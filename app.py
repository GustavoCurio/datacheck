"""Interface de diagnóstico, configuração e exportação do DataCheck."""
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from datacheck.ai import explain_ai
from datacheck.engine import Rules, audit_table
from datacheck.io import read_table
from datacheck.reports import LABELS, explain_local, findings_csv, report_html, report_json

ROOT = Path(__file__).parent
st.set_page_config(page_title="DataCheck · Qualidade de dados", page_icon="🔎", layout="wide")
st.markdown("""<style>
.block-container{max-width:1320px;padding-top:2.5rem}
h1,h2,h3{letter-spacing:-.035em}div[data-testid="stMetric"]{background:#eaf5f5;border:1px solid #cde5e6;border-radius:16px;padding:18px}
.eyebrow{color:#087f8c;font-size:12px;font-weight:700;letter-spacing:.16em}
.lead{color:#526773;font-size:18px;max-width:760px;line-height:1.6}
</style>""", unsafe_allow_html=True)
st.markdown('<div class="eyebrow">DADOS CONFIÁVEIS, DECISÕES MELHORES</div>', unsafe_allow_html=True)
st.title("DataCheck")
st.markdown('<p class="lead">Encontre inconsistências nas suas planilhas, confira as evidências e transforme o diagnóstico em um plano de correção.</p>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Sua base de dados")
    source = st.radio("Fonte", ["Demonstração de pedidos", "Enviar meu arquivo"])
    is_demo = source == "Demonstração de pedidos"
    delimiter = "auto"
    encoding = "utf-8-sig"
    sheet = 0
    if is_demo:
        content = (ROOT / "data/pedidos_demo.csv").read_bytes()
        name = "pedidos_demo.csv"
        st.caption("10 pedidos fictícios, com problemas conhecidos para explorar o sistema.")
        st.download_button("Baixar base de exemplo", content, name, "text/csv")
    else:
        uploaded = st.file_uploader("Arquivo CSV ou XLSX", type=["csv", "xlsx"])
        st.caption("Até 10 MB · 50 mil registros · 50 colunas · 500 mil células.")
        if uploaded is None:
            st.info("Envie um arquivo para começar.")
            st.stop()
        content, name = uploaded.getvalue(), uploaded.name
        if name.lower().endswith(".csv"):
            delimiter = st.selectbox("Separador", ["auto", ",", ";", "\t"], format_func=lambda v: {"auto": "Detectar automaticamente", "\t": "Tabulação"}.get(v, v))
            encoding = st.selectbox("Codificação", ["utf-8-sig", "cp1252"], format_func=lambda v: "UTF-8" if v == "utf-8-sig" else "Windows-1252")
        else:
            sheet = st.number_input("Número da aba", min_value=1, max_value=100, value=1) - 1
    st.divider()
    st.caption("O arquivo é processado na memória desta sessão. A explicação opcional com IA recebe somente contagens, após sua autorização.")

try:
    table = read_table(content, name, delimiter, encoding, int(sheet))
except ValueError as error:
    st.error(str(error))
    st.stop()

dataset_key = hashlib.sha256(content + f"{delimiter}|{encoding}|{sheet}".encode()).hexdigest()[:12]
columns = list(table.columns)
with st.expander("Configurar regras de validação", expanded=not is_demo):
    left, right = st.columns(2)
    with left:
        required = st.multiselect("Campos obrigatórios", columns, default=["pedido_id", "cliente", "valor", "data_compra"] if is_demo else columns, key=f"required_{dataset_key}")
        key = st.selectbox("Identificador único", [None] + columns, index=columns.index("pedido_id") + 1 if is_demo else 0, format_func=lambda v: v or "Não verificar identificador", key=f"key_{dataset_key}")
        numeric = st.multiselect("Colunas numéricas", columns, default=["valor"] if is_demo else [], key=f"numeric_{dataset_key}")
        nonnegative = st.multiselect("Valores não negativos", numeric, default=numeric, key=f"positive_{dataset_key}_{','.join(numeric)}")
        number_style = st.selectbox("Formato dos números", ["decimal_dot", "decimal_comma"], format_func=lambda v: "1,234.56 — decimal com ponto" if v == "decimal_dot" else "1.234,56 — decimal com vírgula", key=f"numbers_{dataset_key}")
    with right:
        dates = st.multiselect("Colunas de data", columns, default=["data_compra", "data_entrega"] if is_demo else [], key=f"dates_{dataset_key}")
        date_format = st.selectbox("Formato das datas em texto", ["%Y-%m-%d", "%d/%m/%Y"], format_func=lambda v: "AAAA-MM-DD" if v == "%Y-%m-%d" else "DD/MM/AAAA", key=f"format_{dataset_key}")
        pair_key = f"{dataset_key}_{','.join(dates)}"
        first = st.selectbox("Data inicial da sequência", [None] + dates, index=dates.index("data_compra") + 1 if is_demo and "data_compra" in dates else 0, format_func=lambda v: v or "Sem comparação", key=f"first_{pair_key}")
        last = st.selectbox("Data final da sequência", [None] + dates, index=dates.index("data_entrega") + 1 if is_demo and "data_entrega" in dates else 0, format_func=lambda v: v or "Sem comparação", key=f"last_{pair_key}")
        exact = st.checkbox("Detectar registros completamente idênticos", value=True, key=f"exact_{dataset_key}")
    st.caption("Números e datas vazios são avaliados apenas quando o campo é obrigatório. Identificadores repetidos consideram o texto exato. Números e datas nativos do Excel são aceitos independentemente do formato textual escolhido.")
    if bool(first) != bool(last) or (first and first == last):
        st.warning("Escolha duas datas distintas para comparar ou deixe as duas sem comparação.")
        st.stop()
    rules = Rules(required=required, key=key, numeric=numeric, nonnegative=nonnegative, dates=dates,
                  date_pairs=[(first, last)] if first and last else [], number_style=number_style,
                  date_format=date_format, exact_duplicates=exact)

token = dataset_key + rules.model_dump_json()
run = st.button("Validar dados", type="primary", icon="🔎")
if run or (is_demo and "result" not in st.session_state):
    with st.spinner("Aplicando as regras e preparando as evidências…"):
        st.session_state.result = audit_table(table, rules)
        st.session_state.result_token = token
        st.session_state.pop("ai_explanation", None)
if st.session_state.get("result_token") != token:
    st.info("Clique em Validar dados para aplicar as regras à base selecionada.")
    st.dataframe(table.head(20), hide_index=True, width="stretch")
    st.stop()

result = st.session_state.result
s = result.summary
st.divider()
metrics = st.columns(4)
for col, label, value in zip(metrics, ["Registros analisados", "Com ocorrências", "Ocorrências", "Sem ocorrências"],
                             [s["rows"], s["affected_rows"], s["findings"], f"{s['rows_without_findings_pct']}%"]):
    col.metric(label, value)
st.caption(f"{name} · {s['columns']} colunas · Motor de validação: {s['elapsed_ms']} ms. Percentual referente somente às regras selecionadas.")

diagnosis, evidence, data_tab, exports = st.tabs(["Diagnóstico", "Evidências", "Dados enviados", "Baixar relatório"])
with diagnosis:
    st.subheader("O que merece atenção")
    if not result.findings:
        st.success(explain_local(result))
    else:
        a, b = st.columns([1.15, 1])
        with a:
            chart = pd.DataFrame([{"Problema": LABELS[rule][0], "Ocorrências": count} for rule, count in s["by_rule"].items()])
            st.bar_chart(chart, x="Problema", y="Ocorrências", horizontal=True, color="#087f8c")
        with b:
            st.write(explain_local(result))
    with st.expander("Explicação com IA"):
        st.write("A IA pode organizar as prioridades usando apenas o total de registros e as contagens por regra. Valores das células, nomes das colunas e o arquivo não são enviados.")
        enabled = bool(os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_MODEL"))
        if not enabled:
            st.info("O diagnóstico local está disponível. A explicação com IA depende da configuração do provedor no servidor.")
        approved = st.checkbox("Autorizo enviar estas contagens agregadas à OpenAI.", key=f"consent_{token}")
        if st.button("Gerar explicação com IA", disabled=not (enabled and approved)):
            try:
                with st.spinner("Organizando as prioridades…"):
                    st.session_state.ai_explanation = explain_ai(result, approved=approved)
            except (ValueError, RuntimeError) as error:
                st.error(str(error))
        if "ai_explanation" in st.session_state:
            explanation = st.session_state.ai_explanation
            st.write(explanation["overview"])
            for priority in explanation["priorities"]:
                st.write(f"**{LABELS[priority['rule']][0]}**")
                st.write(priority["explanation"])
                st.write(priority["action"])
            st.caption("Texto gerado por IA; as contagens e evidências do relatório determinístico são a referência.")
with evidence:
    st.subheader("Cada ocorrência tem uma origem")
    st.caption("Cabeçalho = registro 1; primeiro registro de dados = 2. Em CSV com campos multilinha, a posição é lógica e pode diferir da linha física. Um registro pode ter várias ocorrências.")
    if result.findings:
        selected = st.multiselect("Filtrar por problema", list(s["by_rule"]), format_func=lambda v: LABELS[v][0])
        findings = pd.DataFrame([item for item in result.findings if not selected or item["rule"] in selected])
        st.dataframe(findings.rename(columns={"record": "Registro", "rule": "Regra", "severity": "Severidade", "column": "Coluna", "value": "Valor", "message": "Problema", "suggestion": "Sugestão"}), hide_index=True, width="stretch")
    else:
        st.info("Nenhuma ocorrência para exibir.")
with data_tab:
    st.subheader("Amostra da base original")
    st.caption("Até 200 registros exibidos. As validações não alteram os valores enviados.")
    st.dataframe(table.head(200), hide_index=True, width="stretch")
with exports:
    st.subheader("Seu diagnóstico pronto para compartilhar")
    st.write("Baixe o relatório visual, as evidências para planilhas ou o resultado estruturado para integrar a outros sistemas.")
    a, b, c = st.columns(3)
    a.download_button("Relatório visual · HTML", report_html(result), "datacheck-relatorio.html", "text/html", width="stretch")
    b.download_button("Ocorrências · CSV", findings_csv(result), "datacheck-ocorrencias.csv", "text/csv", width="stretch")
    c.download_button("Resultado completo · JSON", report_json(result), "datacheck-relatorio.json", "application/json", width="stretch")
    st.download_button("Configuração das regras · JSON", json.dumps(result.rules, ensure_ascii=False, indent=2), "regras.json", "application/json")
    st.caption("O CSV de ocorrências neutraliza textos que podem ser interpretados como fórmulas. O JSON preserva os valores originais.")
st.caption("DataCheck · Python + SQL · Validação rastreável por registro")
