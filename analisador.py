import time
from collections import deque
import numpy as np
import serial
from scipy.signal import butter, filtfilt, find_peaks, resample_poly
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec


class ProcessadorSinal:
    G = 9.80665  # m/s^2 - aceleracao da gravidade (para converter m/s^2 -> g)

    def __init__(self, frequencia_max=30):
        self.frequencia_max = frequencia_max

    def filtrar(self, sinal, fs, ordem=5):
        nyq = 0.5 * fs
        normal_cutoff = self.frequencia_max / nyq
        b, a = butter(ordem, normal_cutoff, btype='low')
        return filtfilt(b, a, sinal)

    def fft(self, sinal, fs):
        sinal_ac = sinal - np.mean(sinal)
        valores = np.fft.fft(sinal_ac)
        n = len(sinal)
        freq = np.fft.fftfreq(n, d=1 / fs)
        f_plot = freq[:n // 2]
        modulo = np.abs(valores[:n // 2]) * (2.0 / n)
        return f_plot, modulo

    @staticmethod
    def eixo_principal(ax, ay, az):
        """
        Projeta o movimento 3D no eixo de MAIOR variância (PCA).

        Por que isto é melhor do que escolher X/Y/Z fixo ou usar a magnitude:
        - vs eixo fixo (ex.: X): encontra sozinho a direção dominante do
          movimento, então não importa como o sensor está girado no corpo;
        - vs magnitude sqrt(x²+y²+z²): mantém o sinal LINEAR. A magnitude é
          não-linear e distorce o espectro (cria harmônicos / dobra a
          frequência aparente), o que atrapalha a leitura da FFT.

        Retorna um sinal 1D (a projeção no eixo principal).
        """
        M = np.column_stack([ax, ay, az]).astype(float)
        M = M - M.mean(axis=0)               # centra cada eixo
        _, _, Vt = np.linalg.svd(M, full_matrices=False)
        direcao = Vt[0]                       # 1º componente principal
        # Convencao de sinal: a maior componente do vetor fica sempre positiva.
        # Sem isto, o sinal do PCA e arbitrario e "pisca"/inverte entre frames
        # no tempo real, bugando o grafico do Sinal Principal.
        if direcao[np.argmax(np.abs(direcao))] < 0:
            direcao = -direcao
        return M @ direcao

    @classmethod
    def para_g(cls, sinal):
        """
        Converte aceleracao de m/s^2 (Arduino) para g (unidade do PADS).
        Use SO se for comparar AMPLITUDE com o PADS; para frequencia
        nao faz diferenca (a divisao por constante nao muda a FFT).
        """
        return np.asarray(sinal) / cls.G

    @staticmethod
    def remover_gravidade(sinal):
        """
        Remove a componente DC (gravidade/offset) subtraindo a media,
        deixando o sinal AC-coupled como o do PADS. Para orientacao do
        sensor que muda muito, um filtro passa-altas seria mais robusto.
        """
        sinal = np.asarray(sinal)
        return sinal - np.mean(sinal)


class PainelGraficos:
    SPEC = [
        ('principal', 'Sinal Principal', 'b-', 'Aceleração ($m/s^2$)', 'Tempo (s)'),
        ('x', 'Eixo X', 'g-', 'Aceleração ($m/s^2$)', 'Tempo (s)'),
        ('y', 'Eixo Y', 'darkorange', 'Aceleração ($m/s^2$)', 'Tempo (s)'),
        ('z', 'Eixo Z', 'purple', 'Aceleração ($m/s^2$)', 'Tempo (s)'),
        ('fft', 'Analise na Frequencia', 'r-', 'Magnitude', 'Frequência (Hz)'),
    ]
    EIXOS_TEMPO = ('principal', 'x', 'y', 'z')

    def __init__(self, tamanho_janela=512):
        self.tamanho_janela = tamanho_janela
        self.fig = plt.figure(figsize=(14, 8))
        gs = GridSpec(2, 6, figure=self.fig)
        self.eixos = {
            'principal': self.fig.add_subplot(gs[0, 0:3]),
            'fft': self.fig.add_subplot(gs[0, 3:6]),
            'x': self.fig.add_subplot(gs[1, 0:2]),
            'y': self.fig.add_subplot(gs[1, 2:4]),
            'z': self.fig.add_subplot(gs[1, 4:6]),
        }
        self.linhas = {}
        for key, titulo, cor, ylabel, xlabel in self.SPEC:
            ax = self.eixos[key]
            ax.set_title(titulo)
            ax.set_ylabel(ylabel)
            ax.set_xlabel(xlabel)
            self.linhas[key], = ax.plot([], [], cor)

    def init_limites(self):
        for key in self.EIXOS_TEMPO:
            self.eixos[key].set_ylim(-1, 1)
            self.eixos[key].set_xlim(0, self.tamanho_janela)
        self.eixos['fft'].set_xlim(0, 1)
        self.eixos['fft'].set_ylim(0, 1)
        return self.linhas_tuple()

    def linhas_tuple(self):
        return tuple(self.linhas.values())

    def atualizar_dados(self, tempo, sinais, fft):
        f_plot, modulo = fft
        for key in self.EIXOS_TEMPO:
            self.linhas[key].set_data(tempo, sinais[key])
        self.linhas['fft'].set_data(f_plot, modulo)

    def ajustar_eixo(self, key, sinal):
        ax = self.eixos[key]
        if np.max(sinal) > ax.get_ylim()[1]:
            ax.set_ylim(ax.get_ylim()[0], np.max(sinal) * 1.1)
        if np.min(sinal) < ax.get_ylim()[0]:
            ax.set_ylim(np.min(sinal) * 1.1, ax.get_ylim()[1])

    def ajustar_fft(self, f_plot, modulo):
        ax = self.eixos['fft']
        if np.max(modulo) > ax.get_ylim()[1]:
            ax.set_ylim(0, np.max(modulo) * 1.2)
        if ax.get_xlim()[1] < np.max(f_plot):
            ax.set_xlim(0, np.max(f_plot))

    def ajustar_xlim_tempo(self, t_inicio, t_fim):
        for key in self.EIXOS_TEMPO:
            self.eixos[key].set_xlim(t_inicio, t_fim)

    def fixar_limites(self, tempo, sinais, fft):
        f_plot, modulo = fft
        for key in self.EIXOS_TEMPO:
            s = np.asarray(sinais[key])
            lo, hi = float(np.min(s)), float(np.max(s))
            margem = (hi - lo) * 0.1            # 10% do range do proprio sinal
            if margem == 0:                     # sinal constante: evita eixo nulo
                margem = abs(hi) * 0.1 or 1e-6
            self.eixos[key].set_xlim(0, np.max(tempo))
            self.eixos[key].set_ylim(lo - margem, hi + margem)
        self.eixos['fft'].set_xlim(0, np.max(f_plot))
        self.eixos['fft'].set_ylim(0, np.max(modulo) * 1.1)

    def marcar_tremor(self, banda, freq_dominante=None):
        """Destaca a banda de tremor e a frequência dominante no gráfico da FFT."""
        ax = self.eixos['fft']
        ax.axvspan(banda[0], banda[1], color='red', alpha=0.12,
                   label=f'Banda tremor {banda[0]}-{banda[1]} Hz')
        if freq_dominante is not None and not np.isnan(freq_dominante):
            ax.axvline(freq_dominante, color='k', linestyle='--', linewidth=1)
            ax.annotate(f'{freq_dominante:.2f} Hz',
                        xy=(freq_dominante, ax.get_ylim()[1] * 0.9),
                        fontsize=8, ha='left')
        ax.legend(fontsize=7, loc='upper right')


class AquisicaoSerial:
    def __init__(self, porta, baud, timeout=0.1):
        self.porta = porta
        self.baud = baud
        self.timeout = timeout
        self.ser = None

    def abrir(self):
        try:
            self.ser = serial.Serial(self.porta, baudrate=self.baud, timeout=self.timeout)
            print("Conectado! Lendo dados em tempo real...")
        except Exception as e:
            print(f"Erro: {e}")
            time.sleep(11)
            raise SystemExit

    def disponivel(self):
        return self.ser.in_waiting > 0

    def ler(self):
        try:
            linha = self.ser.readline().decode('utf-8').strip()
            if not linha:
                return None
            partes = linha.split(',')
            return {
                'ace_x': float(partes[0]),
                'ace_y': float(partes[1]),
                'ace_z': float(partes[2]),
                't': float(partes[3]) / 1000,
            }
        except Exception:
            return None

    def fechar(self):
        if self.ser:
            self.ser.close()


class BufferDados:
    def __init__(self, tamanho_janela, gravidade=9.81):
        self.tamanho_janela = tamanho_janela
        self.dados = deque(maxlen=tamanho_janela)
        self.acex = deque(maxlen=tamanho_janela)
        self.acey = deque(maxlen=tamanho_janela)
        self.acez = deque(maxlen=tamanho_janela)
        self.tempo = deque([0], maxlen=tamanho_janela)
        self.intervalos = deque(maxlen=10)
        self.media_inicial = [gravidade] * 10
        self.tempo_zero = 0
        self.fs = 0
        self.n_total = 0  # total de amostras ja recebidas (nao zera com a janela)

    def adicionar(self, leitura):
        # A magnitude e calculada aqui (o Arduino so manda os 3 eixos).
        mag = np.sqrt(leitura['ace_x'] ** 2 + leitura['ace_y'] ** 2 + leitura['ace_z'] ** 2)
        ace = mag - np.mean(self.media_inicial)
        dt = leitura['t'] - self.tempo[-1]
        if len(self.tempo) < 10:
            self.media_inicial.pop(0)
            self.media_inicial.append(mag)
        self.intervalos.append(dt)
        self.acex.append(leitura['ace_x'])
        self.acey.append(leitura['ace_y'])
        self.acez.append(leitura['ace_z'])
        self.dados.append(ace)
        self.tempo.append(leitura['t'])
        self.n_total += 1
        return ace

    def cheio(self):
        return len(self.dados) == self.tamanho_janela

    def atualizar_fs(self):
        # Mediana dos intervalos POSITIVOS: robusta ao 1o intervalo gigante
        # (millis alto) e a resets do Arduino (dt negativo).
        positivos = [d for d in self.intervalos if d > 0]
        if not positivos:
            return
        fs_atual = 1 / np.median(positivos)
        if self.fs < fs_atual:
            self.fs = fs_atual

    def tempo_relativo(self):
        # Eixo de tempo a partir do CONTADOR de amostras (nao do millis):
        # a janela "rola" conforme novos dados chegam, comeca em 0 e nao
        # quebra se o millis() do Arduino resetar.
        n = len(self.dados)
        fs = self.fs if self.fs > 0 else 1.0
        inicio = self.n_total - n
        return (inicio + np.arange(n)) / fs

    def arrays(self):
        return {
            'principal': np.array(self.dados),
            'x': np.array(self.acex),
            'y': np.array(self.acey),
            'z': np.array(self.acez),
        }


class LeitorCSV:
    def __init__(self, caminho):
        self.caminho = caminho

    def carregar(self):
        acex, acey, acez, tempo = [], [], [], []
        with open(self.caminho, "r") as f:
            for linha in f:
                partes = linha.split(',')
                if len(partes) < 4:
                    continue
                # Compatibilidade de formatos:
                #   novo  (4 colunas): x, y, z, t
                #   antigo(5 colunas): ace, x, y, z, t
                if len(partes) >= 5:
                    ix, iy, iz, it = 1, 2, 3, 4
                else:
                    ix, iy, iz, it = 0, 1, 2, 3
                acex.append(float(partes[ix]))
                acey.append(float(partes[iy]))
                acez.append(float(partes[iz]))
                tempo.append(float(partes[it]))
        acex, acey, acez = np.array(acex), np.array(acey), np.array(acez)
        tempo = np.array(tempo)
        dados = np.sqrt(acex ** 2 + acey ** 2 + acez ** 2)  # magnitude (compat.)

        # fs robusto: mediana dos intervalos POSITIVOS. Ignora o tempo alto
        # inicial do millis() e eventuais resets do Arduino no meio da gravacao.
        dt = np.diff(tempo)
        dt = dt[dt > 0]
        fs = 1.0 / np.median(dt) if len(dt) else 100.0

        # Tempo reconstruido do indice e do fs: sempre comeca em 0 e e
        # crescente, mesmo que o millis() tenha comecado alto ou resetado.
        tempo_limpo = np.arange(len(dados)) / fs

        return {
            'dados': dados,
            'acex': acex,
            'acey': acey,
            'acez': acez,
            'tempo': tempo_limpo,
            'fs': fs,
        }


class LeitorPADS:
    def __init__(self, caminho, fs=100.0):
        self.caminho = caminho
        self.fs = fs

    def carregar(self, tarefa_idx=0, pulso='Left'):
        # O arquivo binário pré-processado do PADS tem formato (132, 976)
        matriz = np.fromfile(self.caminho, dtype=np.float32).reshape(132, 976)
        
        # São 12 canais por tarefa.
        # offset 0 para Left wrist, offset 6 para Right wrist.
        offset = 0 if pulso.lower() == 'left' else 6
        base_idx = 12 * tarefa_idx + offset
        
        # PADS vem em g (gravidade removida). A conversao para m/s^2 (x G)
        # e feita por quem chama (menu.py), para nao converter duas vezes.
        acex = matriz[base_idx + 0]
        acey = matriz[base_idx + 1]
        acez = matriz[base_idx + 2]
        
        # O vetor de tempo é gerado com base em fs=100 Hz
        n_amostras = len(acex)
        tempo = np.arange(n_amostras) / self.fs
        
        return {
            'dados': acex, # Apenas para compatibilidade
            'acex': acex,
            'acey': acey,
            'acez': acez,
            'tempo': tempo,
            'fs': self.fs
        }


class LeitorTremorDedo:
    """
    Le CSV de sensor no DEDO (ex.: dataset PosturalTremor).

    Formato bem diferente do CSV do Arduino:
    - separador ';' e cabecalho "Time;X;Y;Z";
    - tempo em "HH:MM:SS.ffffff";
    - X,Y,Z em 'g' (com gravidade), tipicamente a ~2500 Hz.

    Aqui: converte g -> m/s^2 e REAMOSTRA para ~fs_alvo (100 Hz por padrao),
    para ficar igual ao Arduino/PADS e deixar a FFT legivel (2500 Hz daria um
    eixo de frequencia ate 1250 Hz, escondendo o tremor). A reamostragem usa
    filtro anti-aliasing, entao nao perde o tremor (< 50 Hz).
    """

    def __init__(self, caminho, fs_alvo=100.0):
        self.caminho = caminho
        self.fs_alvo = fs_alvo

    @staticmethod
    def _parse_tempo(s):
        # "HH:MM:SS.ffffff" -> segundos
        h, m, resto = s.split(':')
        return int(h) * 3600 + int(m) * 60 + float(resto)

    def carregar(self):
        ts, xs, ys, zs = [], [], [], []
        with open(self.caminho) as f:
            f.readline()  # pula o cabecalho "Time;X;Y;Z"
            for linha in f:
                p = linha.strip().split(';')
                if len(p) < 4:
                    continue
                try:
                    ts.append(self._parse_tempo(p[0]))
                    xs.append(float(p[1]))
                    ys.append(float(p[2]))
                    zs.append(float(p[3]))
                except ValueError:
                    continue

        ts = np.array(ts)
        acex = np.array(xs) * 9.80665   # g -> m/s^2
        acey = np.array(ys) * 9.80665
        acez = np.array(zs) * 9.80665

        # fs original (mediana dos intervalos positivos)
        dt = np.diff(ts)
        dt = dt[dt > 0]
        fs_orig = 1.0 / np.median(dt) if len(dt) else self.fs_alvo

        # Reamostra para ~fs_alvo (decimacao com anti-aliasing)
        fator = max(1, int(round(fs_orig / self.fs_alvo)))
        if fator > 1:
            acex = resample_poly(acex, 1, fator)
            acey = resample_poly(acey, 1, fator)
            acez = resample_poly(acez, 1, fator)
            fs = fs_orig / fator
        else:
            fs = fs_orig

        dados = np.sqrt(acex ** 2 + acey ** 2 + acez ** 2)  # magnitude
        tempo = np.arange(len(dados)) / fs
        return {
            'dados': dados,
            'acex': acex,
            'acey': acey,
            'acez': acez,
            'tempo': tempo,
            'fs': fs,
        }


class MetricasParkinson:
    """
    Métricas quantitativas extraídas do sinal de aceleração.

    ATENÇÃO: são medidas DESCRITIVAS / de apoio à análise, NÃO um diagnóstico.
    As faixas de frequência e qualquer interpretação precisam ser calibradas e
    validadas com dados reais antes de uso clínico. O tremor de repouso
    parkinsoniano costuma ficar em torno de 4-6 Hz.

    Há dois grupos de métricas:
    - TREMOR (domínio da frequência): freq. dominante, índice de tremor, etc.
    - BRADICINESIA (domínio do tempo): taxa de movimento, decremento de
      amplitude e regularidade — mais úteis em tarefas repetitivas como o
      finger-tapping (bater os dedos), onde se avalia a lentidão do gesto.
    """

    # Banda do tremor de repouso parkinsoniano (Hz). Ajuste ao seu protocolo.
    BANDA_TREMOR = (3.5, 7.5)

    # ------------------ Domínio da FREQUÊNCIA (usa o espectro) ------------------

    @staticmethod
    def frequencia_dominante(f, espectro, banda=None):
        """Frequência (Hz) do maior pico do espectro dentro de uma banda."""
        mask = (f > 0.5) if banda is None else (f >= banda[0]) & (f <= banda[1])
        if not np.any(mask):
            return np.nan
        idx = np.argmax(espectro[mask])
        return float(f[mask][idx])

    @staticmethod
    def potencia_banda(f, espectro, f_low, f_high):
        """Potência (soma de magnitude²) numa faixa de frequência."""
        mask = (f >= f_low) & (f <= f_high)
        return float(np.sum(espectro[mask] ** 2))

    @classmethod
    def indice_tremor(cls, f, espectro, banda=None):
        """
        Fração da energia total que cai na banda de tremor (0 a 1).
        Mais alto => sinal mais concentrado na faixa do tremor.
        """
        banda = banda or cls.BANDA_TREMOR
        p_tremor = cls.potencia_banda(f, espectro, banda[0], banda[1])
        p_total = cls.potencia_banda(f, espectro, 0.5, f[-1])
        if p_total <= 0:
            return np.nan
        return p_tremor / p_total

    @staticmethod
    def centroide_espectral(f, espectro):
        """Frequência média ponderada pela potência (Hz) — 'centro de massa'."""
        mask = f > 0.5
        pot = espectro[mask] ** 2
        if np.sum(pot) <= 0:
            return np.nan
        return float(np.sum(f[mask] * pot) / np.sum(pot))

    # ---------------------------- Domínio do TEMPO ----------------------------

    @staticmethod
    def detectar_movimentos(sinal, fs, distancia_min_s=0.15, proeminencia=None):
        """
        Detecta picos do sinal (ex.: cada toque num teste de finger-tapping,
        ou cada ciclo do tremor).
        - distancia_min_s: tempo mínimo entre picos (limita a taxa máxima);
        - proeminencia: destaque mínimo do pico (padrão = metade do desvio).
        Retorna os índices dos picos. Ajuste os parâmetros ao seu protocolo.
        """
        sinal = np.asarray(sinal)
        if proeminencia is None:
            proeminencia = 0.5 * np.std(sinal)
        distancia = max(1, int(distancia_min_s * fs))
        picos, _ = find_peaks(sinal, distance=distancia, prominence=proeminencia)
        return picos

    @staticmethod
    def taxa_movimento(picos, fs):
        """
        Movimentos por segundo (Hz). Em bradicinesia tende a CAIR.
        Para tremor contínuo equivale à frequência do tremor; para
        finger-tapping equivale à cadência das batidas.
        """
        if len(picos) < 2:
            return np.nan
        intervalos = np.diff(picos) / fs
        return float(1.0 / np.mean(intervalos))

    @staticmethod
    def decremento_amplitude(sinal, picos):
        """
        Decremento de amplitude ao longo do movimento repetitivo — marcador
        clássico de bradicinesia (efeito de sequência: o gesto vai 'encolhendo').
        Retorna a queda percentual entre o 1º e o último terço dos picos.
        Positivo => a amplitude diminuiu ao longo do tempo.
        """
        if len(picos) < 6:
            return np.nan
        amps = np.abs(np.asarray(sinal)[picos])
        n = len(amps) // 3
        if n == 0:
            return np.nan
        inicio = np.mean(amps[:n])
        fim = np.mean(amps[-n:])
        if inicio <= 0:
            return np.nan
        return float((inicio - fim) / inicio * 100.0)

    @staticmethod
    def regularidade_ritmo(picos, fs):
        """
        Coeficiente de variação dos intervalos entre picos (CV = desvio/média).
        Menor => ritmo mais regular. PD costuma aumentar a variabilidade.
        """
        if len(picos) < 3:
            return np.nan
        intervalos = np.diff(picos) / fs
        media = np.mean(intervalos)
        if media <= 0:
            return np.nan
        return float(np.std(intervalos) / media)

    # ----------------------------- Relatório -----------------------------

    @classmethod
    def relatorio(cls, sinal, fs, f, espectro, banda_tremor=None):
        """Calcula todas as métricas e devolve um dicionário."""
        banda_tremor = banda_tremor or cls.BANDA_TREMOR
        picos = cls.detectar_movimentos(sinal, fs)
        return {
            'fs_Hz': fs,
            'duracao_s': len(sinal) / fs,
            'freq_dominante_Hz': cls.frequencia_dominante(f, espectro, banda_tremor),
            'freq_dominante_global_Hz': cls.frequencia_dominante(f, espectro),
            'centroide_espectral_Hz': cls.centroide_espectral(f, espectro),
            'indice_tremor': cls.indice_tremor(f, espectro, banda_tremor),
            'n_movimentos': int(len(picos)),
            'taxa_movimento_Hz': cls.taxa_movimento(picos, fs),
            'decremento_amplitude_%': cls.decremento_amplitude(sinal, picos),
            'regularidade_CV': cls.regularidade_ritmo(picos, fs),
        }

    ROTULOS = {
        'fs_Hz': 'Frequencia de amostragem (Hz)',
        'duracao_s': 'Duracao do registro (s)',
        'freq_dominante_Hz': 'Freq. dominante na banda tremor (Hz)',
        'freq_dominante_global_Hz': 'Freq. dominante global (Hz)',
        'centroide_espectral_Hz': 'Centroide espectral (Hz)',
        'indice_tremor': 'Indice de tremor (0-1)',
        'n_movimentos': 'Numero de movimentos detectados',
        'taxa_movimento_Hz': 'Taxa de movimento (Hz)',
        'decremento_amplitude_%': 'Decremento de amplitude (%)',
        'regularidade_CV': 'Irregularidade do ritmo (CV)',
    }

    @staticmethod
    def imprimir_relatorio(rel):
        """Imprime o relatório formatado no terminal."""
        rotulos = MetricasParkinson.ROTULOS
        print('\n' + '=' * 52)
        print('  RELATORIO DE ANALISE  (apoio, NAO diagnostico)')
        print('=' * 52)
        for k, v in rel.items():
            nome = rotulos.get(k, k)
            if isinstance(v, float):
                print(f'  {nome:<40} {v:>9.3f}')
            else:
                print(f'  {nome:<40} {v:>9}')
        print('=' * 52 + '\n')
