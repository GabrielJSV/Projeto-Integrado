"""
App unico: menu com Tempo Real (Arduino) e Analisar Arquivo (CSV / PADS).
Ao fechar a janela dos graficos, o relatorio aparece numa interface.
"""
import os
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
import serial
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from analisador import (ProcessadorSinal, PainelGraficos, AquisicaoSerial,
                        BufferDados, LeitorCSV, LeitorPADS, MetricasParkinson)


# ====================== CONFIGURACAO ======================
BAUD = 115200
PORTA = 'COM10'
TAMANHO_JANELA = 256
FREQUENCIA_MAX = 30
BANDA_TREMOR = (3.5, 7.5)

TAREFAS_PADS = [
    "0. Relaxed (repouso, olhos fechados)",
    "1. Repouso calculando serial sevens",
    "2. Levantar e estender os bracos",
    "3. Manter os bracos levantados",
    "4. Segurar peso de 1 kg",
    "5. Apontar o indicador para a mao do examinador",
    "6. Beber de um copo",
    "7. Cruzar e estender os dois bracos",
    "8. Encostar os dois indicadores",
    "9. Tocar o nariz com o indicador",
    "10. Entrainment (bater os pes acompanhando o ritmo)",
]


# ====================== INTERFACE: RELATORIO ======================
def mostrar_relatorio_gui(rel, subtitulo=""):
    """Mostra o relatorio numa janela (tabela parametro -> valor)."""
    win = tk.Tk()
    win.title("Relatorio de Analise")
    win.geometry("560x440")

    tk.Label(win, text="RELATORIO DE ANALISE",
             font=("Segoe UI", 15, "bold")).pack(pady=(14, 0))
    tk.Label(win, text="(apoio a analise — NAO e diagnostico)",
             fg="gray").pack()
    if subtitulo:
        tk.Label(win, text=subtitulo, fg="#335").pack(pady=(2, 0))

    cols = ("param", "valor")
    tree = ttk.Treeview(win, columns=cols, show="headings", height=12)
    tree.heading("param", text="Parametro")
    tree.heading("valor", text="Valor")
    tree.column("param", width=380, anchor="w")
    tree.column("valor", width=140, anchor="e")
    tree.pack(fill="both", expand=True, padx=12, pady=10)

    for k, v in rel.items():
        nome = MetricasParkinson.ROTULOS.get(k, k)
        if isinstance(v, float):
            valor = "—" if np.isnan(v) else f"{v:.3f}"
        else:
            valor = str(v)
        tree.insert("", "end", values=(nome, valor))

    tk.Button(win, text="Fechar", width=14, command=win.destroy).pack(pady=(0, 14))
    win.mainloop()


def _alerta(titulo, msg, erro=False):
    root = tk.Tk()
    root.withdraw()
    (messagebox.showerror if erro else messagebox.showinfo)(titulo, msg, parent=root)
    root.destroy()


def _pedir_tarefa_pulso(parent):
    """Dialogo para escolher a tarefa (0-10) e o punho do PADS."""
    dlg = tk.Toplevel(parent)
    dlg.title("Opcoes do PADS")
    dlg.grab_set()
    res = {'ok': False, 'tarefa': 0, 'pulso': 'Left'}

    tk.Label(dlg, text="Tarefa:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
    cb_t = ttk.Combobox(dlg, values=TAREFAS_PADS, state="readonly", width=44)
    cb_t.current(0)
    cb_t.grid(row=0, column=1, padx=10, pady=10)

    tk.Label(dlg, text="Punho:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
    cb_p = ttk.Combobox(dlg, values=["Esquerdo (L)", "Direito (R)"],
                        state="readonly", width=44)
    cb_p.current(0)
    cb_p.grid(row=1, column=1, padx=10, pady=10)

    def confirmar():
        res['ok'] = True
        res['tarefa'] = cb_t.current()
        res['pulso'] = 'Left' if cb_p.current() == 0 else 'Right'
        dlg.destroy()

    tk.Button(dlg, text="OK", width=12, command=confirmar).grid(row=2, column=0, pady=12)
    tk.Button(dlg, text="Cancelar", width=12, command=dlg.destroy).grid(row=2, column=1, pady=12)
    parent.wait_window(dlg)
    return res


# ====================== PROCESSAMENTO + GRAFICOS ======================
def _processar_e_plotar(d, subtitulo=""):
    """Roda PCA + FFT + metricas, mostra os graficos e devolve o relatorio."""
    fs = d['fs']
    tempo_plot = d['tempo'] - d['tempo'][0]
    proc = ProcessadorSinal(frequencia_max=FREQUENCIA_MAX)

    sinal = proc.filtrar(proc.eixo_principal(d['acex'], d['acey'], d['acez']), fs, ordem=2)
    f_plot, modulo = proc.fft(sinal, fs)

    print(f"\n{subtitulo}")
    print("Frequencia dominante por eixo (banda de tremor):")
    for nm, dd in (('X', d['acex']), ('Y', d['acey']), ('Z', d['acez'])):
        fe, me = proc.fft(proc.filtrar(dd, fs, ordem=2), fs)
        print(f"  Eixo {nm}: {MetricasParkinson.frequencia_dominante(fe, me, BANDA_TREMOR):.2f} Hz")

    rel = MetricasParkinson.relatorio(sinal, fs, f_plot, modulo, BANDA_TREMOR)
    MetricasParkinson.imprimir_relatorio(rel)

    sinais = {'principal': sinal, 'x': d['acex'], 'y': d['acey'], 'z': d['acez']}
    painel = PainelGraficos()
    painel.fixar_limites(tempo_plot, sinais, (f_plot, modulo))
    painel.atualizar_dados(tempo_plot, sinais, (f_plot, modulo))
    painel.marcar_tremor(BANDA_TREMOR, rel['freq_dominante_Hz'])
    plt.tight_layout()
    plt.show()              # bloqueia ate fechar a janela
    plt.close(painel.fig)
    return rel


# ====================== OPCAO 1: ANALISAR ARQUIVO ======================
def analisar_arquivo():
    root = tk.Tk()
    root.withdraw()
    caminho = filedialog.askopenfilename(
        parent=root,
        title="Escolha o arquivo (CSV do Arduino ou .bin do PADS)",
        filetypes=[("CSV ou PADS", "*.csv *.bin"), ("Todos os arquivos", "*.*")],
    )
    if not caminho:
        root.destroy()
        return

    if caminho.lower().endswith('.bin'):
        r = _pedir_tarefa_pulso(root)
        if not r['ok']:
            root.destroy()
            return
        d = LeitorPADS(caminho).carregar(tarefa_idx=r['tarefa'], pulso=r['pulso'])
        # PADS vem em g; converte para m/s^2 (igual ao Arduino)
        for k in ('acex', 'acey', 'acez', 'dados'):
            d[k] = d[k] * ProcessadorSinal.G
        subt = f"PADS  |  {TAREFAS_PADS[r['tarefa']]}  |  punho {r['pulso']}"
    else:
        d = LeitorCSV(caminho).carregar()
        subt = os.path.basename(caminho)

    root.destroy()
    rel = _processar_e_plotar(d, subt)
    mostrar_relatorio_gui(rel, subt)


# ====================== OPCAO 2: TEMPO REAL ======================
def tempo_real():
    serial_dev = AquisicaoSerial(PORTA, BAUD)
    try:
        serial_dev.ser = serial.Serial(PORTA, baudrate=BAUD, timeout=0.1)
    except Exception as e:
        _alerta("Erro de conexao", f"Nao consegui abrir {PORTA}.\n\n{e}", erro=True)
        return
    print("Conectado! Lendo dados em tempo real...")

    buffer = BufferDados(TAMANHO_JANELA)
    proc = ProcessadorSinal(frequencia_max=FREQUENCIA_MAX)
    painel = PainelGraficos(tamanho_janela=TAMANHO_JANELA)

    hoje = datetime.today()
    nome_csv = f"dados_{hoje.day}_{hoje.month}_{hoje.hour}h{hoje.minute}.csv"
    arquivo = open(nome_csv, "w")

    def init():
        return painel.init_limites()

    def update(frame):
        while serial_dev.disponivel():
            leitura = serial_dev.ler()
            if leitura is None:
                continue
            buffer.adicionar(leitura)
            arquivo.write(f"{leitura['ace_x']},{leitura['ace_y']},{leitura['ace_z']},{leitura['t']}\n")
            arquivo.flush()

        if not buffer.cheio():
            return painel.linhas_tuple()

        buffer.atualizar_fs()
        tempo_plot = buffer.tempo_relativo()
        arrays = buffer.arrays()
        sinal = proc.filtrar(proc.eixo_principal(arrays['x'], arrays['y'], arrays['z']),
                             buffer.fs, ordem=2)
        f_plot, modulo = proc.fft(sinal, buffer.fs)
        arrays['principal'] = sinal

        painel.atualizar_dados(tempo_plot, arrays, (f_plot, modulo))
        painel.ajustar_fft(f_plot, modulo)
        for key in PainelGraficos.EIXOS_TEMPO:
            painel.ajustar_eixo(key, arrays[key])
        painel.ajustar_xlim_tempo(tempo_plot[0], tempo_plot[-1])
        return painel.linhas_tuple()

    ani = FuncAnimation(painel.fig, update, init_func=init, blit=False,
                        interval=20, cache_frame_data=False)
    plt.tight_layout()
    plt.show()              # bloqueia ate fechar a janela
    plt.close(painel.fig)
    del ani

    serial_dev.fechar()
    arquivo.close()

    # Relatorio sobre TODO o registro: re-le o CSV que acabou de ser gravado.
    # (A janela de 256 e usada apenas para o grafico ao vivo.)
    d = LeitorCSV(nome_csv).carregar()
    if len(d['acex']) >= 50:
        fs = d['fs']
        sinal = proc.filtrar(proc.eixo_principal(d['acex'], d['acey'], d['acez']), fs, ordem=2)
        f_plot, modulo = proc.fft(sinal, fs)
        rel = MetricasParkinson.relatorio(sinal, fs, f_plot, modulo, BANDA_TREMOR)
        MetricasParkinson.imprimir_relatorio(rel)
        mostrar_relatorio_gui(rel, f"Tempo real — registro inteiro ({nome_csv})")
    else:
        _alerta("Sem dados", "Nao houve dados suficientes para o relatorio.")


# ====================== MENU PRINCIPAL ======================
def _menu():
    root = tk.Tk()
    root.title("Analise de Tremor / Bradicinesia")
    root.geometry("380x300")
    escolha = {'acao': None}

    def set_acao(a):
        escolha['acao'] = a
        root.destroy()

    tk.Label(root, text="Analise de Tremor", font=("Segoe UI", 16, "bold")).pack(pady=(24, 2))
    tk.Label(root, text="Escolha uma opcao:", fg="gray").pack(pady=(0, 18))

    tk.Button(root, text="Tempo Real (Arduino)", width=28, height=2,
              command=lambda: set_acao('tempo_real')).pack(pady=6)
    tk.Button(root, text="Analisar Arquivo (CSV / PADS)", width=28, height=2,
              command=lambda: set_acao('arquivo')).pack(pady=6)
    tk.Button(root, text="Sair", width=28, command=lambda: set_acao('sair')).pack(pady=(16, 0))

    root.mainloop()
    return escolha['acao']


def main():
    while True:
        acao = _menu()
        if acao == 'tempo_real':
            tempo_real()
        elif acao == 'arquivo':
            analisar_arquivo()
        else:
            break


if __name__ == '__main__':
    main()
