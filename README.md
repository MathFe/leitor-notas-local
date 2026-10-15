# Leitor local de notas fiscais e comprovantes de Pix

Projeto para o **DEV Hacktoberfest 2026 — desafio "Side Hustle"**: IA open-source rodando 100% local
(Ollama + Qwen 2.5 / Qwen 2.5-VL) para ler notas fiscais, cupons NFC-e, comprovantes de Pix e recibos
de uma contadora autônoma e transformar tudo numa planilha Excel, sem nenhum dado sair da máquina (LGPD).

- [`leitor_notas/`](leitor_notas/) — o aplicativo (pipeline, validação, avaliação e interface Streamlit). Veja o README dele.
- [`amostras-mariana/`](amostras-mariana/) — 10 documentos **fictícios** + gabarito para avaliar a acurácia.

Resultado nas amostras: **95% dos campos corretos**, com os 2 documentos problemáticos enviados para revisão.

Licença: [MIT](LICENSE).
