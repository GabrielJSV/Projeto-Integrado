# Análise de Tremor e Bradicinesia (Parkinson)

Ferramenta para analisar sinais de **aceleração** e extrair indicadores de
**tremor** e **bradicinesia** associados à doença de Parkinson. Funciona com
duas fontes de dados:

- **Arduino + MPU6050** — aquisição em tempo real (e gravação em CSV);
- **Dataset PADS** (*Parkinson's Disease Smartwatch*) — arquivos binários `.bin`.

O sinal é filtrado, projetado no eixo de maior movimento (PCA), transformado
para o domínio da frequência (FFT) e resumido num relatório de métricas.

> ⚠️ **Aviso:** as métricas são **descritivas / de apoio**, **não** constituem
> diagnóstico. Faixas de frequência e limiares precisam ser calibrados e
> validados com dados reais antes de qualquer interpretação clínica.

---

## Requisitos

- Python 3.x
- Bibliotecas: `numpy`, `scipy`, `matplotlib`, `pyserial`

```bash
pip install numpy scipy matplotlib pyserial
```

Para o Arduino: bibliotecas **Adafruit MPU6050** e **Adafruit Unified Sensor**.

---

## Estrutura dos arquivos

| Arquivo | O que é |
|---|---|
| `menu.py` | **Programa principal** — menu com Tempo Real e Analisar Arquivo |
| `analisador.py` | Todas as classes (processamento, gráficos, leitura, métricas) |
| `sketch_apr23a/sketch_apr23a.ino` | Firmware do Arduino (lê o MPU6050 e envia pela serial) |

### Classes em `analisador.py`

- **`ProcessadorSinal`** — filtro passa-baixas, FFT, eixo principal (PCA) e
  conversões de unidade (`G`, `para_g`, `remover_gravidade`).
- **`PainelGraficos`** — monta e atualiza os 5 gráficos (sinal principal,
  X, Y, Z e FFT).
- **`AquisicaoSerial`** — abre e lê a porta serial do Arduino.
- **`BufferDados`** — buffer circular usado no tempo real (janela da FFT).
- **`LeitorCSV`** — lê CSV do Arduino (detecta 4 ou 5 colunas).
- **`LeitorPADS`** — lê o `.bin` do PADS (devolve em `g`).
- **`MetricasParkinson`** — calcula e imprime o relatório de métricas.

---

## Formato dos dados

### CSV do Arduino
4 colunas, **uma amostra por linha**:

```
ace_x, ace_y, ace_z, t
```

- Acelerações em **m/s²**; tempo **`t` em segundos**.
- (Arquivos antigos com 5 colunas — `ace, x, y, z, t` — ainda são lidos.)
- O `t` gravado é o `millis()` do Arduino. Na leitura, o tempo é **reconstruído**
  a partir do índice e do `fs`, então sempre começa em 0 (veja "limitações").

### Binário do PADS (`.bin`)
Matriz `float32` de forma **(132, 976)**:

- **132 = 11 tarefas × 12 canais**; **976 amostras** por canal (~9,76 s a 100 Hz).
- 12 canais por tarefa: `[Esq: acc_x,y,z, gyr_x,y,z | Dir: acc_x,y,z, gyr_x,y,z]`.
- Dados em **`g`, com a gravidade removida**. O `menu.py` multiplica por
  `G` (9,80665) para deixar em **m/s²**, igual ao Arduino.
- Só o **acelerômetro** é usado (o giroscópio é ignorado).

As 11 tarefas do PADS:

| Idx | Tarefa |
|---|---|
| 0 | Relaxed (repouso, olhos fechados) |
| 1 | Repouso calculando "serial sevens" |
| 2 | Levantar e estender os braços |
| 3 | Manter os braços levantados |
| 4 | Segurar peso de 1 kg |
| 5 | Apontar o indicador para a mão do examinador |
| 6 | Beber de um copo |
| 7 | Cruzar e estender os dois braços |
| 8 | Encostar os dois indicadores |
| 9 | Tocar o nariz com o indicador |
| 10 | Entrainment (bater os pés acompanhando o ritmo) |

---

## Como rodar

Tudo passa pelo programa principal:

```bash
python menu.py
```

Abre um **menu** com duas opções:

### Tempo Real (Arduino)
1. Carregue `sketch_apr23a/sketch_apr23a.ino` na placa.
2. No topo do `menu.py`, ajuste `PORTA` (ex.: `COM10`) e `BAUD` (115200).
3. Clique em **Tempo Real** — mostra os gráficos ao vivo e grava um CSV
   `dados_<data>.csv`. Ao fechar a janela, o **relatório** aparece numa interface.

### Analisar Arquivo (CSV / PADS)
Clique em **Analisar Arquivo** e escolha o arquivo no seletor:
- **CSV** (Arduino) → análise direta;
- **`.bin`** (PADS) → um diálogo pede a **tarefa (0–10)** e o **punho (L/R)**.

Ao fechar os gráficos, o **relatório** aparece numa janela.

---

## O relatório de métricas

Mostrado ao fechar os gráficos (e também impresso no terminal). **10 parâmetros**
em 3 grupos:

### Contexto do sinal
| Parâmetro | Significado |
|---|---|
| Frequência de amostragem (Hz) | Amostras por segundo (define o limite de Nyquist = fs/2). |
| Duração do registro (s) | Tamanho do sinal = nº de amostras ÷ fs. |

### Frequência / tremor
| Parâmetro | Significado |
|---|---|
| Freq. dominante na banda tremor (Hz) | Maior pico **dentro** da banda de tremor — a "frequência do tremor" (PD ≈ 4–6 Hz). |
| Freq. dominante global (Hz) | Maior pico em **todo** o espectro. Se for bem diferente da anterior, a maior energia não está no tremor. |
| Centroide espectral (Hz) | "Centro de massa" do espectro (média das frequências ponderada pela energia). |
| Índice de tremor (0–1) | Fração da energia total que está na banda de tremor. Maior = mais dominado por tremor. |

### Bradicinesia (movimento repetitivo)
| Parâmetro | Significado |
|---|---|
| Nº de movimentos detectados | Quantos picos foram achados (ex.: cada batida de um *finger-tapping*). |
| Taxa de movimento (Hz) | Movimentos por segundo. **Na bradicinesia, tende a cair.** |
| Decremento de amplitude (%) | Quanto a amplitude diminui do início ao fim (1º vs último terço dos picos). **Marcador clássico** — positivo = o gesto "encolhe". |
| Irregularidade do ritmo (CV) | Variação dos intervalos entre picos. 0 = ritmo regular; maior = mais irregular. |

---

## Configurações principais

| Constante | Onde | Padrão | O que faz |
|---|---|---|---|
| `PORTA` / `BAUD` | `menu.py` | COM10 / 115200 | Porta serial do Arduino. |
| `FREQUENCIA_MAX` | `menu.py` | 30 Hz | Corte do filtro passa-baixas (< fs/2). |
| `BANDA_TREMOR` | `menu.py` | (3.5, 7.5) Hz | Faixa considerada como tremor. |
| `TAMANHO_JANELA` | `menu.py` | 256 | Nº de pontos por FFT no tempo real. |
| `fs` do PADS | `LeitorPADS` | 100 Hz | Frequência de amostragem assumida do PADS. |

**Unidades:** todo o pipeline trabalha em **m/s²** e **segundos**.

---

## Como mudar a taxa de aquisição do Arduino

A taxa de amostragem (leituras por segundo) é definida em **um único lugar**: o
período entre leituras no firmware.

### 1. No Arduino — `sketch_apr23a/sketch_apr23a.ino`
Mude a constante **`PERIODO_MS`** (período entre amostras, em milissegundos):

```cpp
const unsigned long PERIODO_MS = 10;  // ~100 Hz
```

A taxa resultante é, aproximadamente:

```
taxa (Hz) ≈ 1000 / PERIODO_MS
```

| `PERIODO_MS` | Taxa aproximada |
|---|---|
| 5  | ~200 Hz |
| 10 | ~100 Hz |
| 20 | ~50 Hz  |
| 50 | ~20 Hz  |

> É "aproximada" porque o loop e a serial têm um custo; o valor real fica um
> pouco menor — por isso o Python **mede** a taxa em vez de assumir (veja abaixo).

### 2. No Python — normalmente NÃO precisa mexer
O `fs` é **calculado automaticamente** a partir da coluna de tempo (mediana dos
intervalos), tanto no tempo real (`BufferDados.atualizar_fs`) quanto na leitura
de CSV (`LeitorCSV.carregar`). Você muda a taxa no Arduino e o Python se ajusta
sozinho — e a mediana mantém o `fs` correto mesmo que o `millis()` do Arduino
comece alto ou resete no meio da gravação.

> ⚠️ **Exceção — limite de Nyquist.** O filtro só funciona até **metade da
> taxa** (fs/2). Se você **baixar** a taxa, ajuste no topo do `menu.py`:
> ```python
> FREQUENCIA_MAX = 30        # precisa ser < fs/2
> BANDA_TREMOR  = (3.5, 7.5) # precisa caber abaixo de fs/2
> ```
> Ex.: a 50 Hz, fs/2 = 25 Hz, então `FREQUENCIA_MAX = 30` **quebra** — use ~20.

### 3. Se também mudar o baud rate (ex.: para Bluetooth)
Taxa de amostragem e baud são coisas diferentes, mas se trocar o baud no
Arduino, troque junto no Python — os dois têm que bater:

| Onde | Constante |
|---|---|
| `sketch_apr23a.ino` | `Serial.begin(115200);` |
| `menu.py` | `BAUD = 115200` |

---

## Limitações / notas honestas

- **Não é diagnóstico** — apoio à análise apenas.
- A unidade do PADS foi **inferida** como `g` (valores pequenos, gravidade
  removida). **Confirme na documentação/paper do PADS**; se for outra, o fator
  de conversão muda.
- O `fs = 100 Hz` do PADS também é uma suposição — confirme. Toda frequência
  escala proporcionalmente a esse valor.
- **1 MPU6050 = 1 punho.** O PADS tem 2 (esquerdo e direito); o Arduino replica
  apenas um.
- Para **frequência** do tremor, a unidade não importa (m/s² ou g dão o mesmo);
  ela só afeta comparações de **amplitude**.
- O `millis()` do Arduino pode começar alto ou **resetar** no meio da gravação.
  O tempo é reconstruído do índice ÷ fs (sempre começa em 0), mas se houve um
  reset, fica ~1 amostra "estranha" no ponto do salto.
