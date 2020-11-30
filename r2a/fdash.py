from player.parser import *
from r2a.ir2a import IR2A
import time
import random
import statistics as stat
import math

class fdash(IR2A):
    def __init__(self, id):
        IR2A.__init__(self, id)
        self.parsed_mpd = ''
        self.qi = []
        self.seg_size = 0 # guarda o tamanho do ultimo segmento em bits
        self.seg_time = 0 # guarda o tamanho do ultimo segmento em segundos
        self.start = 0 # guarda o tempo em que foi iniciada a requisição do segmento
        self.end = 0 # guarda o tempo em que chegou a resposta da requisição do segmento
        self.throughputs = [] #guarda os throughputs de todos os segmentos
        self.t_i = 0 # guarda o buffering time do último segmento
        self.delta_t_i = 0 # guarda a diferença do buffering time do último segmento e do penúltimo segmento
        self.T = 35 # constante que guarda o target buffering time, definido no artigo como 35s
        self.d = 60 # constante que guarda o tempo que vai ser levado em conta para calcular o throughput médio, 60s.
        self.response_number = 0 #guarda a quantidade de segmentos que chegaram



    # as funções short, close e long tomam como parâmetro o buffering time t_i
    # que é o tempo que o último segmento vai esperar até começar a ser exibido.
    # Elas recebem o buffering time t_i e retornam
    # o grau de pertencimento (de 0 a 1) da diferença desse buffering time e o buffering time limite T
    # a uma dada situação.
    # Por exemplo, dado um tempo t_i de buffer, se a diferença entre o tempo de buffer limite (self.T)
    # e esse tempo t_i for pequena então short(t_i) vai ser bem grande, próximo de 1. Já se a diferença entre o tempo de buffer limite (self.T)
    # e o tempo t_i for grande, o short(t_i) vai ser próximo de 0 e long(t_i) vai ser próximo de 1.
    # O comportamento dessas funções ta definido na figura 2 do artigo.
    def short_v(self, t_i):
        if t_i < 2*self.T/3:
            return 1
        if t_i >= 2*self.T/3 and t_i < self.T:
            return (-3*t_i)/self.T + 3
        if t_i >= self.T:
            return 0

    def close_v(self, t_i):
        if t_i < 2*self.T/3:
            return 0
        if t_i >= 2*self.T/3 and t_i < self.T:
            return (3*t_i/self.T)-2
        if t_i >= self.T and t_i <= 4*self.T:
            return (-1*t_i/(3*self.T)) + 4

    def long_v(self, t_i):
        if t_i < self.T:
            return 0
        if t_i >= self.T and t_i < 4*self.T:
            return t_i/(3*self.T)-1
        if t_i >= 4*self.T:
            return 1

    # as funções falling, steady e risiing tomam como parâmetro a diferença dos buffering times t_i e t_(i-1).
    # Essas funções recebem o delta buffering time (t_i - t_(i-1)) e retornam
    # o grau de pertencimento (de 0 a 1) desse delta a uma dada "situação".
    # Por exemplo, dado um delta buffering time qualquer, se ele for negativo, então falling(delta_t_i) vai ser alto.
    # Se o delta for positivo, então falling(delta_t_i) vai ser próximo de zero e rising(delta_t_i) vai ser alto.
    # O comportamento dessas funções também ta definido na figura 2 do artigo.

    def falling(self, delta_t_i):
        if delta_t_i < -2*self.T/3:
            return 1
        if delta_t_i >= -2*self.T/3 and delta_t_i < 0:
            return -3*delta_t_i/(2*self.T)
        if delta_t_i >= 0:
            return 0

    def steady(self, delta_t_i):
        if delta_t_i < -2*self.T/3:
            return 0
        if delta_t_i >= -2*self.T/3 and delta_t_i < 0:
            return 3*delta_t_i/(2*self.T) + 1
        if delta_t_i >= 0 and delta_t_i < 4*self.T:
            return -1*delta_t_i/(4*self.T) + 1
        if delta_t_i >= 4*self.T:
            return 0

    def rising(self, delta_t_i):
        if delta_t_i < 0:
            return 0
        if delta_t_i >= 0 and delta_t_i < 4*self.T:
            return delta_t_i/(4*self.T)
        if delta_t_i >= 4*self.T:
            return 1

    # a definição dessa função f segue exatamente o que ta no artigo.
    def f(self, t_i, delta_t_i):
        # as r1,r2,etc são definidas como o mínimo entre as duas funções
        # que definem a regra (exatamente como ta no artigo)
        r1 = min(self.short_v(t_i), self.falling(delta_t_i))
        r2 = min(self.close_v(t_i), self.falling(delta_t_i))
        r3 = min(self.long_v(t_i), self.falling(delta_t_i))
        r4 = min(self.short_v(t_i), self.steady(delta_t_i))
        r5 = min(self.close_v(t_i), self.steady(delta_t_i))
        r6 = min(self.long_v(t_i), self.steady(delta_t_i))
        r7 = min(self.short_v(t_i), self.rising(delta_t_i))
        r8 = min(self.close_v(t_i), self.rising(delta_t_i))
        r9 = min(self.long_v(t_i), self.rising(delta_t_i))

        # essas definições também são exatamente o que ta no artigo

        R = math.sqrt(r1**2)
        SR = math.sqrt(r2**2+r4**2)
        NC = math.sqrt(r3**2+r5**2+r7**2)
        SI = math.sqrt(r6**2+r8**2)
        I = math.sqrt(r9**2)

        f = (0.25*R + 0.5*SR + 1*NC + 1.5*SI + 2*I)/(SR+R+NC+SI+I)

        # f é definida no artigo como esse quociente
        return f

    def handle_xml_request(self, msg):
        self.send_down(msg)

    def handle_xml_response(self, msg):
        self.parsed_mpd = parse_mpd(msg.get_payload())
        self.qi = self.parsed_mpd.get_qi()

        self.send_up(msg)

    def handle_segment_size_request(self, msg):
        #se ainda não tiverem nem duas respostas não tem como calcular o delta buffering time (ou seja, nao tem como calcular f())
        #entao faço o request com a menor qualidade
        if self.response_number < 2:
            msg.add_quality_id(self.qi[0])
        else:
            download_time = self.end - self.start
            # o throughput é o quociente entre o tamanho do segmento, registrado na chegada do segmento
            # em handle_segment_size_request e o tempo de download definido acima.
            throughput = self.seg_size/download_time

            #salva o throughput do último seguimento nessa lista de throughputs
            self.throughputs.append(throughput)

            # definição do limite da próxima bitrate, dada pelo artigo.
            bitrate_limit = self.f(self.t_i, self.delta_t_i)*stat.mean(self.throughputs[(-1*int(self.d/self.seg_time)):]) #throughput medio dos ultimos d segundos
            print(bitrate_limit)
            print(self.qi)
            # esse loop escolhe a maior resolução disponível que é menor que o bitrate limit, como estipulado no paper
            i = 0
            choosen_bitrate = self.qi[0]
            while self.qi[i] < bitrate_limit:
                choosen_bitrate = self.qi[i]
                i = i + 1

            msg.add_quality_id(choosen_bitrate)

        #começa a contar o tempo pro segmento que vai ser requisitado
        self.start = time.time()
        self.send_down(msg)


    def handle_segment_size_response(self, msg):
        self.end = time.time()

        self.seg_size = msg.get_bit_length()

        #se ainda não tiverem nem duas respostas não tem como calcular o delta
        if self.response_number < 2:
            self.seg_time = msg.get_segment_size() #guarda o tamanho do segmento de resposta em segundos
            self.t_i = self.response_number*self.seg_time
        else:
            self.delta_t_i = self.whiteboard.get_amount_video_to_play()*self.seg_time - self.t_i
            self.t_i = self.whiteboard.get_amount_video_to_play()*self.seg_time

        self.response_number += 1
        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass
