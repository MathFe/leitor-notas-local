"""
Gera 10 documentos FICTÍCIOS (notas fiscais e comprovantes de Pix) para testar
o pipeline de leitura. Todos os nomes, CNPJs e chaves são inventados.

Saída:
  documentos/   -> os 10 arquivos (4 PDFs com texto + 6 imagens "fotografadas")
  gabarito.json -> o que o pipeline DEVERIA extrair de cada arquivo
  categorias.json

Uso: python gerar_amostras.py
Requisitos: pip install reportlab pillow numpy qrcode
"""
import json
import random
from pathlib import Path

import numpy as np
import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

random.seed(42)
BASE = Path(__file__).parent
OUT = BASE / "documentos"
OUT.mkdir(exist_ok=True)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def fonte(tam, estilo=""):
    nomes = {"": "DejaVuSans.ttf", "b": "DejaVuSans-Bold.ttf",
             "mono": "DejaVuSansMono.ttf", "i": "DejaVuSans-Oblique.ttf"}
    windows = {"": "arial.ttf", "b": "arialbd.ttf", "mono": "consola.ttf", "i": "ariali.ttf"}
    for caminho in (FONT_DIR + nomes[estilo], "C:/Windows/Fonts/" + windows[estilo]):
        try:
            return ImageFont.truetype(caminho, tam)
        except OSError:
            pass
    return ImageFont.load_default(tam)


# ---------------------------------------------------------------- utilidades
CATEGORIAS = [
    "Aluguel",
    "Energia, água e telefone",
    "Combustível e transporte",
    "Matéria-prima e insumos",
    "Material de escritório e limpeza",
    "Manutenção e reparos",
    "Serviços de terceiros",
    "Alimentação",
    "Impostos e taxas",
    "Equipamentos",
    "Receita (entrada)",
    "Outros",
]


def gerar_cnpj():
    base = [random.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
                  [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        soma = sum(d * p for d, p in zip(base, pesos))
        resto = soma % 11
        base.append(0 if resto < 2 else 11 - resto)
    s = "".join(map(str, base))
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"


def chave_acesso(cnpj, aamm, modelo, numero):
    """Chave de 44 dígitos no formato da NF-e/NFC-e, com DV módulo 11."""
    so_num = "".join(c for c in cnpj if c.isdigit())
    corpo = f"35{aamm}{so_num}{modelo}001{numero:09d}1{random.randint(0, 10**8 - 1):08d}"
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(corpo)))
    dv = 11 - (soma % 11)
    dv = 0 if dv >= 10 else dv
    chave = corpo + str(dv)
    assert len(chave) == 44
    return chave


def fmt_chave(ch):
    return " ".join(ch[i:i + 4] for i in range(0, 44, 4))


def brl(v):
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def id_e2e():
    return "E" + "".join(random.choice("0123456789ABCDEF") for _ in range(31))


def fotografar(img, angulo, ruido=8, blur=0.6, sombra=True, escala=1.0):
    """Simula foto de celular: fundo de mesa, rotação, sombra, ruído e desfoque."""
    img = img.convert("RGB")
    if escala != 1.0:
        img = img.resize((int(img.width * escala), int(img.height * escala)))
    margem = 140
    fundo = Image.new("RGB", (img.width + 2 * margem, img.height + 2 * margem), (118, 96, 74))
    fundo.paste(img, (margem, margem))
    fundo = fundo.rotate(angulo, resample=Image.BICUBIC, expand=False, fillcolor=(118, 96, 74))
    arr = np.asarray(fundo).astype(np.int16)
    if sombra:
        h, w = arr.shape[:2]
        grad = np.linspace(1.0, 0.72, w)[None, :, None] * np.linspace(0.95, 1.0, h)[:, None, None]
        arr = (arr * grad).astype(np.int16)
    arr = arr + np.random.normal(0, ruido, arr.shape).astype(np.int16)
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if blur:
        out = out.filter(ImageFilter.GaussianBlur(blur))
    return out


def qr_img(texto, tam=170):
    q = qrcode.make(texto, box_size=4, border=1)
    return q.resize((tam, tam))


# ------------------------------------------------- 1) comprovantes Pix em PDF
def pix_pdf(nome_arq, *, tipo, data, hora, valor, pagador, recebedor, banco, descricao=""):
    c = canvas.Canvas(str(OUT / nome_arq), pagesize=(90 * mm, 160 * mm))
    w, h = 90 * mm, 160 * mm
    c.setFillColorRGB(0.13, 0.42, 0.36)
    c.rect(0, h - 22 * mm, w, 22 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(8 * mm, h - 12 * mm, banco)
    c.setFont("Helvetica", 8)
    c.drawString(8 * mm, h - 17 * mm, "DOCUMENTO FICTÍCIO - USO EM TESTES")
    c.setFillColorRGB(0, 0, 0)
    y = h - 32 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(8 * mm, y, "Comprovante de Pix " + ("enviado" if tipo == "enviado" else "recebido"))
    y -= 9 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(8 * mm, y, brl(valor))
    y -= 7 * mm
    c.setFont("Helvetica", 8.5)
    c.drawString(8 * mm, y, f"{data} às {hora}")
    y -= 9 * mm

    def bloco(titulo, linhas):
        nonlocal y
        c.setFont("Helvetica-Bold", 9)
        c.drawString(8 * mm, y, titulo)
        y -= 5 * mm
        c.setFont("Helvetica", 8.5)
        for l in linhas:
            c.drawString(8 * mm, y, l)
            y -= 4.5 * mm
        y -= 3 * mm

    bloco("Quem pagou", [pagador["nome"], f"{pagador['doc_tipo']}: {pagador['doc']}", pagador["inst"]])
    bloco("Quem recebeu", [recebedor["nome"], f"{recebedor['doc_tipo']}: {recebedor['doc']}",
                           recebedor["inst"], f"Chave Pix: {recebedor['chave']}"])
    if descricao:
        bloco("Descrição", [descricao])
    bloco("Identificador da transação", [id_e2e()[:22], id_e2e()[22:] + id_e2e()[:10]])
    c.save()


# ---------------------------------------------------- 2) DANFE simplificado
def danfe_pdf(nome_arq, emit, dest, data, itens, numero):
    c = canvas.Canvas(str(OUT / nome_arq), pagesize=A4)
    w, h = A4
    total = sum(q * v for _, q, v in itens)
    aamm = data[8:10] + data[3:5]
    ch = chave_acesso(emit["cnpj"], aamm, "55", numero)
    c.setLineWidth(0.8)
    c.rect(15 * mm, h - 55 * mm, w - 30 * mm, 40 * mm)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, h - 25 * mm, emit["nome"])
    c.setFont("Helvetica", 8.5)
    c.drawString(20 * mm, h - 31 * mm, emit["end"])
    c.drawString(20 * mm, h - 36 * mm, f"CNPJ: {emit['cnpj']}")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(130 * mm, h - 25 * mm, "DANFE")
    c.setFont("Helvetica", 8)
    c.drawString(130 * mm, h - 30 * mm, "Documento Auxiliar da NF-e")
    c.drawString(130 * mm, h - 35 * mm, f"Nº {numero:09d}  Série 001")
    c.drawString(20 * mm, h - 44 * mm, "CHAVE DE ACESSO")
    c.setFont("Courier-Bold", 9.5)
    c.drawString(20 * mm, h - 50 * mm, fmt_chave(ch))
    c.setFont("Helvetica", 7)
    c.drawString(20 * mm, h - 60 * mm, "DOCUMENTO FICTÍCIO GERADO PARA TESTES - SEM VALOR FISCAL")
    y = h - 72 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "DESTINATÁRIO")
    c.setFont("Helvetica", 8.5)
    c.drawString(20 * mm, y - 5 * mm, f"{dest['nome']}   CNPJ: {dest['cnpj']}")
    c.drawString(20 * mm, y - 10 * mm, f"Data de emissão: {data}")
    y -= 24 * mm
    c.setFont("Helvetica-Bold", 8.5)
    for x, t in [(20, "DESCRIÇÃO"), (120, "QTD"), (140, "V. UNIT"), (170, "V. TOTAL")]:
        c.drawString(x * mm, y, t)
    c.line(20 * mm, y - 2 * mm, w - 20 * mm, y - 2 * mm)
    c.setFont("Helvetica", 8.5)
    for desc, q, v in itens:
        y -= 6 * mm
        c.drawString(20 * mm, y, desc)
        c.drawString(120 * mm, y, str(q))
        c.drawString(140 * mm, y, brl(v))
        c.drawString(170 * mm, y, brl(q * v))
    y -= 12 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(130 * mm, y, f"VALOR TOTAL DA NOTA: {brl(total)}")
    c.save()
    return ch, round(total, 2)


# ------------------------------------------------ 3) imagens (desenhadas)
def danfe_imagem(emit, dest, data, itens, numero):
    total = sum(q * v for _, q, v in itens)
    ch = chave_acesso(emit["cnpj"], data[8:10] + data[3:5], "55", numero)
    img = Image.new("RGB", (1240, 1000), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 1200, 300], outline="black", width=3)
    d.text((60, 60), emit["nome"], font=fonte(34, "b"), fill="black")
    d.text((60, 110), emit["end"], font=fonte(22), fill="black")
    d.text((60, 145), f"CNPJ: {emit['cnpj']}", font=fonte(24), fill="black")
    d.text((900, 60), "DANFE", font=fonte(40, "b"), fill="black")
    d.text((900, 115), f"Nº {numero:09d}", font=fonte(22), fill="black")
    d.text((60, 200), "CHAVE DE ACESSO", font=fonte(20, "b"), fill="black")
    d.text((60, 235), fmt_chave(ch), font=fonte(27, "mono"), fill="black")
    d.text((60, 320), "DOCUMENTO FICTÍCIO - SEM VALOR FISCAL", font=fonte(18), fill="gray")
    d.text((60, 370), f"DESTINATÁRIO: {dest['nome']}  CNPJ {dest['cnpj']}", font=fonte(22), fill="black")
    d.text((60, 405), f"Data de emissão: {data}", font=fonte(22), fill="black")
    y = 470
    for x, t in [(60, "DESCRIÇÃO"), (700, "QTD"), (820, "V. UNIT"), (1010, "TOTAL")]:
        d.text((x, y), t, font=fonte(22, "b"), fill="black")
    d.line([60, y + 35, 1180, y + 35], fill="black", width=2)
    for desc, q, v in itens:
        y += 50
        d.text((60, y), desc, font=fonte(22), fill="black")
        d.text((700, y), str(q), font=fonte(22), fill="black")
        d.text((820, y), brl(v), font=fonte(22), fill="black")
        d.text((1010, y), brl(q * v), font=fonte(22), fill="black")
    d.text((620, y + 90), f"VALOR TOTAL: {brl(total)}", font=fonte(32, "b"), fill="black")
    return img, ch, round(total, 2)


def cupom_nfce(emit, data, hora, itens, numero, pagamento):
    total = sum(q * v for _, q, v in itens)
    ch = chave_acesso(emit["cnpj"], data[8:10] + data[3:5], "65", numero)
    W = 560
    img = Image.new("RGB", (W, 1250), (247, 245, 238))
    d = ImageDraw.Draw(img)
    f, fb, fm = fonte(20, "mono"), fonte(22, "b"), fonte(18, "mono")

    def centro(t, y, ft=f):
        tw = d.textlength(t, font=ft)
        d.text(((W - tw) / 2, y), t, font=ft, fill=(40, 40, 40))

    y = 25
    centro(emit["nome"], y, fb); y += 34
    centro(f"CNPJ {emit['cnpj']}", y); y += 28
    centro(emit["end"][:40], y, fm); y += 34
    centro("DOCUMENTO FICTÍCIO DA NFC-e", y, fm); y += 26
    centro("Documento Auxiliar - teste", y, fm); y += 30
    d.text((20, y), "-" * 44, font=fm, fill="gray"); y += 26
    for desc, q, v in itens:
        d.text((20, y), desc[:30], font=f, fill=(40, 40, 40)); y += 26
        d.text((40, y), f"{q} x {v:.2f}".replace(".", ","), font=fm, fill=(40, 40, 40))
        tt = f"{q * v:.2f}".replace(".", ",")
        d.text((W - 20 - d.textlength(tt, font=f), y), tt, font=f, fill=(40, 40, 40)); y += 30
    d.text((20, y), "-" * 44, font=fm, fill="gray"); y += 28
    d.text((20, y), "VALOR TOTAL R$", font=fb, fill=(20, 20, 20))
    tt = f"{total:.2f}".replace(".", ",")
    d.text((W - 20 - d.textlength(tt, font=fb), y), tt, font=fb, fill=(20, 20, 20)); y += 34
    d.text((20, y), f"FORMA PGTO: {pagamento}", font=fm, fill=(40, 40, 40)); y += 34
    centro(f"NFC-e nº {numero:06d} Série 001", y, fm); y += 24
    centro(f"Emissão: {data} {hora}", y, fm); y += 30
    centro("Consulte pela Chave de Acesso", y, fm); y += 24
    centro(fmt_chave(ch)[:27], y, fm); y += 22
    centro(fmt_chave(ch)[27:], y, fm); y += 30
    img.paste(qr_img(f"TESTE|chNFe={ch}|vNF={total:.2f}"), ((W - 170) // 2, y))
    img = img.crop((0, 0, W, y + 200))
    return img, ch, round(total, 2)


def print_pix_celular(*, data, hora, valor, recebedor, cnpj, banco, descricao):
    img = Image.new("RGB", (720, 1480), (250, 250, 252))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 720, 70], fill=(20, 20, 24))
    d.text((30, 20), "10:42", font=fonte(26, "b"), fill="white")
    d.text((560, 20), "5G  87%", font=fonte(24), fill="white")
    d.rectangle([0, 70, 720, 190], fill=(124, 58, 237))
    d.text((40, 110), banco, font=fonte(34, "b"), fill="white")
    d.ellipse([300, 240, 420, 360], fill=(34, 197, 94))
    d.text((335, 262), "✓", font=fonte(64, "b"), fill="white")
    d.text((185, 390), "Pix enviado!", font=fonte(44, "b"), fill=(20, 20, 24))
    d.text((60, 480), "Valor", font=fonte(26), fill="gray")
    d.text((60, 515), brl(valor), font=fonte(56, "b"), fill=(20, 20, 24))
    y = 640
    for rot, val in [("Para", recebedor), ("CNPJ", cnpj), ("Data", f"{data} - {hora}"),
                     ("Mensagem", descricao), ("Tipo", "Pix por chave aleatória")]:
        d.text((60, y), rot, font=fonte(24), fill="gray")
        d.text((60, y + 34), val, font=fonte(30), fill=(20, 20, 24))
        d.line([60, y + 90, 660, y + 90], fill=(225, 225, 230), width=2)
        y += 115
    d.text((60, y + 30), "Documento fictício - teste", font=fonte(20), fill="gray")
    d.rounded_rectangle([60, 1330, 660, 1420], radius=40, fill=(124, 58, 237))
    d.text((230, 1352), "Compartilhar", font=fonte(32, "b"), fill="white")
    return img


def recibo_manual(*, numero, valor, pagador, recebedor, cpf_mascarado, referente, data_ext, cidade):
    img = Image.new("RGB", (1300, 720), (252, 250, 240))
    d = ImageDraw.Draw(img)
    for yy in range(160, 700, 56):
        d.line([40, yy, 1260, yy], fill=(190, 205, 230), width=2)
    d.rectangle([20, 20, 1280, 700], outline=(80, 80, 80), width=3)
    d.text((60, 50), "RECIBO", font=fonte(54, "b"), fill=(30, 30, 30))
    d.text((520, 62), f"Nº {numero}", font=fonte(32), fill=(30, 30, 30))
    d.rectangle([900, 45, 1250, 115], outline=(30, 30, 30), width=2)
    d.text((920, 58), brl(valor), font=fonte(40, "b"), fill=(30, 30, 30))
    caneta = (25, 45, 140)
    linhas = [
        f"Recebi de {pagador}",
        f"a importância de {brl(valor)} ({_extenso(valor)})",
        f"referente a {referente}.",
        f"{cidade}, {data_ext}.",
        "",
        f"__________________________   {recebedor}  CPF {cpf_mascarado}",
    ]
    y = 128
    for l in linhas:
        d.text((60 + random.randint(-4, 4), y), l, font=fonte(30, "i"), fill=caneta)
        y += 56
    d.text((60, 650), "Documento fictício - teste", font=fonte(18), fill="gray")
    return img


def _extenso(v):
    tab = {380.0: "trezentos e oitenta reais", 650.0: "seiscentos e cinquenta reais"}
    return tab.get(v, "valor por extenso")


# ------------------------------------------------------------------- dados
SJC = "São José dos Campos/SP"
cliente = {"nome": "STUDIO BELLA FORMA LTDA (fictício)", "cnpj": gerar_cnpj()}
empresas = {
    "imobiliaria": {"nome": "Imobiliária Vale Azul Ltda", "cnpj": gerar_cnpj()},
    "distribuidora": {"nome": "Distribuidora Paraíba Cosméticos Ltda",
                      "end": "Av. Exemplo, 1000 - Distrito Industrial - " + SJC, "cnpj": gerar_cnpj()},
    "posto": {"nome": "AUTO POSTO SERRA DO MAR LTDA", "end": "Rod. Exemplo, km 145 - Caçapava/SP",
              "cnpj": gerar_cnpj()},
    "restaurante": {"nome": "RESTAURANTE SABOR DO VALE", "end": "R. Fictícia, 210 - Centro - SJC",
                    "cnpj": gerar_cnpj()},
    "papelaria": {"nome": "PAPELARIA E LIMPEZA AQUARIUS", "end": "Av. Inventada, 55 - Jacareí/SP",
                  "cnpj": gerar_cnpj()},
    "refrigeracao": {"nome": "Frio Total Refrigeração ME", "cnpj": gerar_cnpj()},
    "equipamentos": {"nome": "Rede Ar & Energia Equipamentos Ltda",
                 "end": "R. Modelo, 77 - Jardim Fictício - " + SJC, "cnpj": gerar_cnpj()},
}
pj_cliente = {"nome": cliente["nome"], "doc_tipo": "CNPJ", "doc": cliente["cnpj"],
              "inst": "Banco Fictício S.A. - Ag 0001"}

gabarito = []

# 01 - Pix enviado: aluguel (PDF)
pix_pdf("01_pix_aluguel.pdf", tipo="enviado", data="05/10/2026", hora="09:14", valor=3200.00,
        pagador=pj_cliente, banco="Banco Fictício",
        recebedor={"nome": empresas["imobiliaria"]["nome"], "doc_tipo": "CNPJ",
                   "doc": empresas["imobiliaria"]["cnpj"], "inst": "Banco Exemplo S.A.",
                   "chave": "financeiro@valeazul.exemplo"},
        descricao="ALUGUEL OUT/2026 SALA 3")
gabarito.append({"arquivo": "01_pix_aluguel.pdf", "tipo": "pix_enviado", "data": "2026-10-05",
                 "valor": 3200.00, "contraparte": empresas["imobiliaria"]["nome"],
                 "cnpj_contraparte": empresas["imobiliaria"]["cnpj"], "categoria": "Aluguel",
                 "caminho_esperado": "pdf_texto", "deve_revisar": False})

# 02 - Pix recebido: receita (PDF)
pix_pdf("02_pix_recebido_cliente.pdf", tipo="recebido", data="08/10/2026", hora="16:47", valor=450.00,
        pagador={"nome": "Fernanda R. S.", "doc_tipo": "CPF", "doc": "***.482.917-**",
                 "inst": "Banco Digital Exemplo"},
        recebedor={"nome": cliente["nome"], "doc_tipo": "CNPJ", "doc": cliente["cnpj"],
                   "inst": "Banco Fictício S.A.", "chave": cliente["cnpj"]},
        banco="Banco Fictício", descricao="pacote 5 sessoes drenagem")
gabarito.append({"arquivo": "02_pix_recebido_cliente.pdf", "tipo": "pix_recebido", "data": "2026-10-08",
                 "valor": 450.00, "contraparte": "Fernanda R. S.", "cnpj_contraparte": None,
                 "categoria": "Receita (entrada)", "caminho_esperado": "pdf_texto", "deve_revisar": False})

# 03 - Pix enviado: conserto do ar-condicionado (PDF)
pix_pdf("03_pix_manutencao_ar.pdf", tipo="enviado", data="10/10/2026", hora="11:02", valor=680.00,
        pagador=pj_cliente, banco="Banco Fictício",
        recebedor={"nome": empresas["refrigeracao"]["nome"], "doc_tipo": "CNPJ",
                   "doc": empresas["refrigeracao"]["cnpj"], "inst": "Cooperativa Exemplo",
                   "chave": "(12) 9XXXX-0000"},
        descricao="limpeza e recarga gas split")
gabarito.append({"arquivo": "03_pix_manutencao_ar.pdf", "tipo": "pix_enviado", "data": "2026-10-10",
                 "valor": 680.00, "contraparte": empresas["refrigeracao"]["nome"],
                 "cnpj_contraparte": empresas["refrigeracao"]["cnpj"], "categoria": "Manutenção e reparos",
                 "caminho_esperado": "pdf_texto", "deve_revisar": False})

# 04 - DANFE em PDF: insumos
itens_04 = [("Óleo de massagem neutro 1L", 6, 38.90), ("Creme redutor 500g", 4, 72.50),
            ("Lençol descartável rolo 70cm", 10, 24.90)]
ch, tot = danfe_pdf("04_nfe_insumos.pdf", empresas["distribuidora"], cliente, "02/10/2026", itens_04, 18734)
gabarito.append({"arquivo": "04_nfe_insumos.pdf", "tipo": "nfe", "data": "2026-10-02", "valor": tot,
                 "contraparte": empresas["distribuidora"]["nome"],
                 "cnpj_contraparte": empresas["distribuidora"]["cnpj"], "chave_acesso": ch,
                 "categoria": "Matéria-prima e insumos", "caminho_esperado": "pdf_texto",
                 "deve_revisar": False})

# 05 - foto de DANFE: equipamento (imagem torta)
itens_05 = [("Aparelho de radiofrequência RF-200", 1, 2890.00), ("Ponteira facial reposição", 2, 145.00)]
img, ch, tot = danfe_imagem(empresas["equipamentos"], cliente, "07/10/2026", itens_05, 5521)
fotografar(img, angulo=-4.5, ruido=10, blur=0.8).save(OUT / "05_foto_nfe_equipamento.jpg", quality=78)
gabarito.append({"arquivo": "05_foto_nfe_equipamento.jpg", "tipo": "nfe", "data": "2026-10-07", "valor": tot,
                 "contraparte": empresas["equipamentos"]["nome"], "cnpj_contraparte": empresas["equipamentos"]["cnpj"],
                 "chave_acesso": ch, "categoria": "Equipamentos", "caminho_esperado": "imagem_visao",
                 "deve_revisar": False})

# 06 - cupom NFC-e: combustível
img, ch, tot = cupom_nfce(empresas["posto"], "09/10/2026", "07:38",
                          [("GASOLINA COMUM", 1, 248.37)], 402918, "Cartão de débito")
fotografar(img, angulo=3, ruido=9, blur=0.7).save(OUT / "06_cupom_combustivel.jpg", quality=80)
gabarito.append({"arquivo": "06_cupom_combustivel.jpg", "tipo": "nfce", "data": "2026-10-09", "valor": tot,
                 "contraparte": empresas["posto"]["nome"], "cnpj_contraparte": empresas["posto"]["cnpj"],
                 "chave_acesso": ch, "categoria": "Combustível e transporte",
                 "caminho_esperado": "imagem_visao", "deve_revisar": False})

# 07 - cupom NFC-e: almoço
img, ch, tot = cupom_nfce(empresas["restaurante"], "11/10/2026", "12:51",
                          [("PRATO EXECUTIVO", 2, 32.90), ("SUCO NATURAL 500ML", 2, 9.50),
                           ("AGUA S/ GAS", 1, 4.00)], 88123, "Pix")
fotografar(img, angulo=-2, ruido=8, blur=0.6).save(OUT / "07_cupom_restaurante.jpg", quality=80)
gabarito.append({"arquivo": "07_cupom_restaurante.jpg", "tipo": "nfce", "data": "2026-10-11", "valor": tot,
                 "contraparte": empresas["restaurante"]["nome"],
                 "cnpj_contraparte": empresas["restaurante"]["cnpj"], "chave_acesso": ch,
                 "categoria": "Alimentação", "caminho_esperado": "imagem_visao", "deve_revisar": False})

# 08 - print de Pix no celular (PNG, sem foto): serviço de terceiro
img = print_pix_celular(data="12/10/2026", hora="10:41", valor=1250.00,
                        recebedor="Agência Pixel Criativo Ltda (fictícia)", cnpj=(cnpj08 := gerar_cnpj()),
                        banco="Banco Roxo Fictício", descricao="gestao redes sociais outubro")
img.save(OUT / "08_print_pix_marketing.png")
gabarito.append({"arquivo": "08_print_pix_marketing.png", "tipo": "pix_enviado", "data": "2026-10-12",
                 "valor": 1250.00, "contraparte": "Agência Pixel Criativo Ltda (fictícia)",
                 "cnpj_contraparte": cnpj08, "categoria": "Serviços de terceiros",
                 "caminho_esperado": "imagem_visao", "deve_revisar": False})

# 09 - recibo "escrito à mão": serviço de pessoa física
img = recibo_manual(numero="047", valor=380.00, pagador=cliente["nome"], recebedor="Josias P. Lima",
                    cpf_mascarado="***.215.608-**", referente="pintura da recepção e mão de obra",
                    data_ext="3 de outubro de 2026", cidade="São José dos Campos")
fotografar(img, angulo=6, ruido=12, blur=1.0).save(OUT / "09_recibo_pintura.jpg", quality=72)
gabarito.append({"arquivo": "09_recibo_pintura.jpg", "tipo": "recibo", "data": "2026-10-03", "valor": 380.00,
                 "contraparte": "Josias P. Lima", "cnpj_contraparte": None,
                 "categoria": "Manutenção e reparos", "caminho_esperado": "imagem_visao",
                 "deve_revisar": True,
                 "observacao": "Recibo sem CNPJ: a validação deve marcar para revisão."})

# 10 - cupom ruim E de setembro: caso que DEVE ir para revisão
img, ch, tot = cupom_nfce(empresas["papelaria"], "29/09/2026", "17:20",
                          [("PAPEL SULFITE A4 C/500", 3, 27.90), ("DESINFETANTE 5L", 2, 21.50),
                           ("PAPEL TOALHA INTERF C/1000", 4, 18.75)], 15502, "Dinheiro")
ruim = fotografar(img, angulo=11, ruido=22, blur=1.9, escala=0.6)
ruim = ruim.resize((ruim.width // 2, ruim.height // 2)).resize((ruim.width, ruim.height))
ruim.save(OUT / "10_cupom_borrado_setembro.jpg", quality=45)
gabarito.append({"arquivo": "10_cupom_borrado_setembro.jpg", "tipo": "nfce", "data": "2026-09-29",
                 "valor": tot, "contraparte": empresas["papelaria"]["nome"],
                 "cnpj_contraparte": empresas["papelaria"]["cnpj"], "chave_acesso": ch,
                 "categoria": "Material de escritório e limpeza", "caminho_esperado": "imagem_visao",
                 "deve_revisar": True,
                 "observacao": "Foto ruim e data fora do mês de competência (out/2026): deve cair em revisão."})

(BASE / "gabarito.json").write_text(json.dumps({"competencia": "2026-10", "cliente": cliente,
                                                "documentos": gabarito}, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
(BASE / "categorias.json").write_text(json.dumps(CATEGORIAS, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{len(gabarito)} documentos gerados em {OUT}")
