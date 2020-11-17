from player.parser import *
from r2a.ir2a import IR2A
import time
import random
import statistics
import math

class fdash(IR2A):
    def __init__(self, id):
        IR2A.__init__(self, id)
        self.parsed_mpd = ''
        self.qi = []
        self.seg_size = 0 # guarda o tamanho do ultimo segmento em bits
        self.start = 0 # guarda o tempo em que foi iniciada a requisição do segmento
        self.end = 0 # guarda o tempo em que chegou a resposta da requisição do segmento
        self.throughputs = [] #guarda os throughputs de todos os segmentos
        self.t_i = 0 # guarda o buffering time do último segmento
        self.delta_t_i = 0 # guarda a diferença do buffering time do último segmento e do penúltimo segmento
        self.T = 35 # constante que guarda o target buffering time, definido no artigo como 35s
        self.d = 60 # constante que guarda o tempo que vai ser levado em conta para calcular o throughput médio, 60s.


    # as funções short, close e long tomam como parâmetro o buffering time t_i
    # que é o tempo que o último segmento vai esperar até começar a ser exibido.
    # Elas recebem o buffering time t_i e retornam
    # o grau de pertencimento (de 0 a 1) da diferença desse buffering time e o buffering time limite T
    # a uma dada situação.
    # Por exemplo, dado um tempo t_i de buffer, se a diferença entre o tempo de buffer limite (self.T)
    # e esse tempo t_i for pequena então short(t_i) vai ser bem grande, próximo de 1. Já se a diferença entre o tempo de buffer limite (self.T)
    # e o tempo t_i for grande, o short(t_i) vai ser próximo de 0 e long(t_i) vai ser próximo de 1.
    # O comportamento dessas funções ta definido na figura 2 do artigo.
    def short(t_i):
        if t_i < 2*self.T/3:
            return 1
        if t_i >= 2*self.T/3 and t_i <= self.T:
            return (-3*t_i)/self.T + 3

    def close(t_i):
        if t_i >= 2*self.T/3 and t_i < self.T:
            return (3*t_i/self.T)-2
        if t_i >= self.T and t_i <= 4*self.T:
            return (-1*t_i/(3*self.T)) + 4

    def long(t_i):
        if t_i >= self.T and t_i < 4*self.T:
            return t_i/(3*self.T)-1
        if t_i >= 4*self.T:
            return 1

    # as funções falling, steady e risiing tomam como parâmetro a diferença dos buffering times t_i e t_(i-1).
    # Essas funções recebem o delta buffering time (t_i - t_(i-1)) e retornam
    # o grau de pertencimento (de 0 a 1) desse delta a uma dada situação.
    # Por exemplo, dado um delta buffering time, se ele for negativo, então falling(delta_t_i) vai ser alto.
    # Se o delta for positivo, então falling(delta_t_i) vai ser próximo de zero e rising(delta_t_i) vai ser alto.
    # O comportamento dessas funções também ta definido na figura 2 do artigo.

    def falling(delta_t_i):
        if t_i < -2*self.T/3:
            return 1
        if t_i >= -2*self.T/3 and t_i <= 0:
            return -3*t_i/(2*self.T)

    def steady(delta_t_i):
        if t_i >= -2*self.T/3 and t_i < 0:
            return 3*t_i/(2*self.T) + 1
        if t_i >= 0 and t_i < 4*self.T:
            return -1*t_i/(4*self.T) + 1

    def rising(delta_t_i):
        if t_i >= 0 and t_i < 4*self.T:
            return t_i/(4*self.T)
        if t_i >= 4*self.T:
            return 1

    # a definição dessa função f segue exatamente o que ta no artigo.
    def f(t_i, delta_t_i):
        # as r1,r2,etc são definidas como o mínimo entre as duas funções
        # que definem a regra (exatamente como ta no artigo)
        r1 = min(short(t_i), falling(delta_t_i))
        r2 = min(close(t_i), falling(delta_t_i))
        r3 = min(long(t_i), falling(delta_t_i))
        r4 = min(short(t_i), steady(delta_t_i))
        r5 = min(close(t_i), steady(delta_t_i))
        r6 = min(long(t_i), steady(delta_t_i))
        r4 = min(short(t_i), rising(delta_t_i))
        r5 = min(close(t_i), rising(delta_t_i))
        r6 = min(long(t_i), rising(delta_t_i))

        # essas definições também são exatamente o que ta no artigo
        R = math.sqrt(r1**2)
        SR = math.sqrt(r2**2+r4**2)
        NC = math.sqrt(r3**2+r5**2+r7**2)
        SI = math.sqrt(r6**2+r8**2)
        I = math.sqrt(r9**2)

        # f é definida como esse quociente pelo artigo
        return (0.25*R + 0.5*SR + 1*NC + 1.5*SI + 2*I)/(SR+R+NC+SI+I)

    def handle_xml_request(self, msg):
        self.send_down(msg)

    def handle_xml_response(self, msg):
        # getting qi list
        self.parsed_mpd = parse_mpd(msg.get_payload())
        self.qi = self.parsed_mpd.get_qi()

        self.send_up(msg)

    def handle_segment_size_request(self, msg):
        # o tempo de download é a diferença do tempo inicial "self.start" (que foi registrado
        # no momento que o request foi mandado pra baixo, linha 111) e o tempo final "self.end" (que é registrado
        # assim que chega a resposta para o request no handle_segment_size_response)
        download_time = self.end - self.start

        # o throughput é o quociente entre o tamanho do segmento, registrado na chegada do segmento
        # em handle_segment_size_request (linha 118) e o tempo de download definido acima.
        throughput = self.seg_size/download_time

        #salva o throughput do último seguimento nessa lista de throughputs
        self.throughputs.append(throughput)

        # definição da próxima bitrate dada pelo artigo.
        bitrate_limit = f(self.t_i, self.delta_t_i)*mean(self.throughputs[(-1*self.d):]) #mean throughput of last d segments (segments of 1s)

        # esse loop escolhe a maior resolução disponível que é menor que o bitrate limit,
        # como foi definido no artigo
        i = 0
        while q_i[i] < bitrate_limit:
            choosen_bitrate = q_i[i]
            i = i + 1

        # Hora de definir qual qualidade será escolhida
        msg.add_quality_id(choosen_bitrate)

        #começa a contar o tempo pro segmento que vai ser requisitado
        self.start = time.time()
        self.send_down(msg)

    def handle_segment_size_response(self, msg):
        # para de contar o tempo de download do segmento
        self.end = time.time()

        #pega o tamanho do segmento em bits
        self.seg_size = msg.get_bit_length()

        # essas duas linhas abaixo precisam ser definidas, mas não sei ainda como pegar o buffer time atual.
        # esse self.t_i e self.delta_t_i são os parâmetros que
        # o artigo define como os inputs das funções short, close, long (t_i) e das
        # funções falling, steady e rising (delta_t_i)

        # self.delta_t_i = get_current_buffer_time() - self.t_i
        # self.t_i = get_current_buffer_time()

        #manda a mensagem com o segmento pro player
        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass
