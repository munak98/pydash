"""
@author: Manuela Matos Correia de Souza 16/0135281
@author: Gustavo Einstein Soares Oliveira 17/0104630
@author: Gabriel Vitor dos Santos Crispim 15/0010451
"""

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
        self.seg_size = 0 # tamanho do último segmento em bits
        self.seg_time = 0 # tamanho dos segmentos em segundos
        self.start = time.time() # momento em que foi iniciada a requisição do segmento
        self.end = 0 # momento em que chegou a resposta da requisição do segmento
        self.throughputs = [] # lista que guarda os throughputs de todos os segmentos
        self.t_i = 0 # guarda o buffering time do último segmento
        self.delta_t_i = 0 # guarda a diferença do buffering time do último segmento e do penúltimo segmento
        self.T = 20 # target buffering time, usado para calculo das variáveis short, close e long
        self.d = 1 # tempo que vai ser levado em consideração para calcular o throughput médio
        self.response_number = 0 #guarda a quantidade de segmentos que chegaram


    # as funções short, close e long tomam como parâmetro o buffering time t_i
    # que é o tempo que o último segmento vai esperar no buffer até começar a ser exibido.
    # Elas recebem o buffering time t_i e retornam o grau de pertencimento (de 0 a 1)
    # desse buffering time a situações descritas pelas variáveis com relação a um limite T.
    # A definição dessas funções pode ser obtida pelos gráficos da figura 2 do artigo base.
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
            return (-1*t_i/(3*self.T)) + 4/3

    def long_v(self, t_i):
        if t_i < self.T:
            return 0
        if t_i >= self.T and t_i < 4*self.T:
            return t_i/(3*self.T)-1/3
        if t_i >= 4*self.T:
            return 1

    # as funções falling, steady e risiing tomam como parâmetro a diferença dos buffering times t_i e t_(i-1).
    # Essas funções recebem o delta buffering time (t_i - t_(i-1)) e retornam
    # o grau de pertencimento (de 0 a 1) desse delta à situação que a variável descreve.
    # O comportamento dessas funções também está definido na figura 2 do artigo base.

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

    # f é o controlador que determina o fator de aumento ou diminuição
    # da bitrate do segmento i+1. Ela toma como entrada
    # o tempo de buffer e o delta tempo de buffer do segmento i.
    # a definição de f é dada pelas equações 1, 2, 3, 4, 5 e 6 do artigo base.
    def f(self, t_i, delta_t_i):
        # ri é definido como o mínimo entre as duas funções
        # que compõem o antecedente da regra i.
        r1 = min(self.short_v(t_i), self.falling(delta_t_i))
        r2 = min(self.close_v(t_i), self.falling(delta_t_i))
        r3 = min(self.long_v(t_i), self.falling(delta_t_i))
        r4 = min(self.short_v(t_i), self.steady(delta_t_i))
        r5 = min(self.close_v(t_i), self.steady(delta_t_i))
        r6 = min(self.long_v(t_i), self.steady(delta_t_i))
        r7 = min(self.short_v(t_i), self.rising(delta_t_i))
        r8 = min(self.close_v(t_i), self.rising(delta_t_i))
        r9 = min(self.long_v(t_i), self.rising(delta_t_i))

        # essas definições também são exatamente o que ta no artigo.
        R = math.sqrt(r1**2)
        SR = math.sqrt(r2**2+r4**2)
        NC = math.sqrt(r3**2+r5**2+r7**2)
        SI = math.sqrt(r6**2+r8**2)
        I = math.sqrt(r9**2)

        # f é definida como a média ponderada das constantes 0.25, 0.5, 1, 1.5 e 2
        # onde os pesos são as funçoes R, SR, NC, SI e I calculadas acima
        # essa definição também segue o que está descrito no artigo.
        f = (0.25*R + 0.5*SR + 1*NC + 1.5*SI + 2*I)/(SR+R+NC+SI+I)

        return f

    def handle_xml_request(self, msg):
        self.send_down(msg)

    def handle_xml_response(self, msg):
        self.parsed_mpd = parse_mpd(msg.get_payload())
        self.qi = self.parsed_mpd.get_qi()

        self.send_up(msg)

    def handle_segment_size_request(self, msg):
        #se ainda não tiverem duas respostas, não é possível calcular
        # o delta buffering time e, consequentemente, não é possível calcular
        # o fator de aumento ou diminuição f().
        # Portanto, a requisição é feita com a menor qualidade.
        if self.response_number < 2:
            msg.add_quality_id(self.qi[0])
        else:
            # depois das duas primeiras respostas, é possível
            # determinar a próxima bitrate. Ela é definida como o fator
            # de aumento ou diminuição f() multiplicado pela média
            # do throughput dos últimos d segundos.
            bitrate_limit = self.f(self.t_i, self.delta_t_i)*stat.mean(self.throughputs[(-1*int(self.d/self.seg_time)):]) #throughput médio dos ultimos d segundos

            # na verdade, o artigo diz que a próxima bitrate será
            # a maior birate ofertada que é menor que a bitrate limit.
            choosen_bitrate = self.qi[0]
            for rate in self.qi:
                if bitrate_limit > rate:
                    choosen_bitrate = rate

            # políticas para evitar flutuação desnecessária da bitrate.
            # essas políticas não foram implementadas nessa versão do algoritmo.
            # if choosen_bitrate > self.current_rate:
            #     next60_estimate = self.delta_t_i + (stat.mean(self.throughputs[(-1*int(self.d/self.seg_time)):]) / choosen_bitrate - 1) * 60
            #     if next60_estimate < self.T:
            #          choosen_bitrate = self.current_rate
            # elif choosen_bitrate < self.current_rate:
            #     next60_estimate = self.delta_t_i + (stat.mean(self.throughputs[(-1*int(self.d/self.seg_time)):]) / self.current_rate - 1) * 60
            #     if next60_estimate > self.T:
            #          choosen_bitrate = self.current_rate

            msg.add_quality_id(choosen_bitrate)

        self.start = time.time() # começa a contar o tempo de download do segmento
        self.send_down(msg)


    def handle_segment_size_response(self, msg):
        self.end = time.time() # registra o momento que o download termina

        # o throughput é o quociente entre o tamanho do segmento recebido
        # e o tempo de download
        throughput = msg.get_bit_length()/(self.end - self.start)
        self.throughputs.append(throughput)

        #se ainda não tiverem duas respostas, o cálculo de self.delta_t_i não precisa
        # ser feito.
        if self.response_number < 2:
            self.seg_time = msg.get_segment_size() #tamanho do segmento em segundos, só precisa ser feito uma vez já que todos os segmentos terão o mesmo tempo
            # self.t_i = self.response_number*self.seg_time # calcula o tempo de buffer do segmento como a quantidade de
        else:
            self.delta_t_i = self.whiteboard.get_amount_video_to_play()*self.seg_time - self.t_i

        self.t_i = self.whiteboard.get_amount_video_to_play()*self.seg_time # calcula o tempo de buffer do segmento (quantidade de segmentos no buffer vezes o tamanho do buffer)
        self.response_number += 1
        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass
