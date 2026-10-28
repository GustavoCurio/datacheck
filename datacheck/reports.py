"""Relatórios escapados, evidências e explicação local."""
import csv
import html
import io
import json

from .engine import Audit

LABELS = {
    "duplicate_row": ("Registros idênticos", "Confirme se as repetições são esperadas antes de remover registros."),
    "duplicate_key": ("Identificadores repetidos", "Confira a chave e a origem das repetições."),
    "missing_required": ("Campos obrigatórios vazios", "Busque o preenchimento na fonte original."),
    "invalid_number": ("Números inválidos", "Confira o conteúdo e o formato decimal escolhido."),
    "negative_number": ("Valores negativos", "Confira o lançamento conforme a regra de negócio."),
    "invalid_date": ("Datas inválidas", "Confira o calendário e o formato informado."),
    "date_order": ("Sequência de datas", "Verifique se a data final deve ser posterior ou igual à inicial."),
}
FIELDS = ["record", "rule", "severity", "column", "value", "message", "suggestion"]


def explain_local(audit: Audit):
    s = audit.summary
    if not s["findings"]:
        return "Nenhuma ocorrência nas regras selecionadas. Isso não valida regras de negócio que não foram configuradas."
    lines = [f"Foram encontradas {s['findings']} ocorrências em {s['affected_rows']} de {s['rows']} registros."]
    for rule, count in sorted(s["by_rule"].items(), key=lambda item: (-item[1], item[0])):
        label, action = LABELS[rule]
        lines.append(f"{label}: {count} ocorrência(s). {action}")
    return "\n\n".join(lines)


def report_json(audit):
    return json.dumps(audit.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")


def spreadsheet_safe(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def findings_csv(audit):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["registro", "regra", "severidade", "coluna", "valor", "problema", "sugestao"])
    for finding in audit.findings:
        writer.writerow([spreadsheet_safe(finding[field]) for field in FIELDS])
    return buffer.getvalue().encode("utf-8-sig")


def report_html(audit):
    esc = lambda value: html.escape(str(value), quote=True)
    s = audit.summary
    rows = "".join("<tr>" + "".join(f"<td>{esc(item[key])}</td>" for key in FIELDS) + "</tr>" for item in audit.findings)
    rules = esc(json.dumps(audit.rules, ensure_ascii=False, indent=2))
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DataCheck · Relatório de qualidade</title><style>
body{{font:16px system-ui;margin:40px auto;padding:0 24px;max-width:1400px;color:#172b37;background:#f4f8fa}}
h1{{color:#087f8c}}section{{background:white;padding:24px;border-radius:16px;margin:20px 0}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #d7e3e7;padding:9px;text-align:left;overflow-wrap:anywhere}}
thead{{background:#e2f3f2}}pre{{white-space:pre-wrap}}.scroll{{overflow:auto}}
</style><h1>DataCheck</h1><p>Relatório de validação de dados</p>
<section><b>{s['rows']} registros · {s['affected_rows']} com ocorrências · {s['findings']} ocorrências</b>
<p>{s['rows_without_findings_pct']}% dos registros sem ocorrências nas regras selecionadas.</p>
<p>Tempo do motor: {s['elapsed_ms']} ms. Cabeçalho = registro 1; o primeiro registro de dados = 2.
Em CSV, esta é a posição lógica do registro, não a linha física quando há campos multilinha.</p></section>
<section><h2>Diagnóstico</h2><pre>{esc(explain_local(audit))}</pre></section>
<section class="scroll"><h2>Evidências</h2><table><thead><tr><th>Registro</th><th>Regra</th><th>Severidade</th><th>Coluna</th><th>Valor</th><th>Problema</th><th>Sugestão</th></tr></thead><tbody>{rows}</tbody></table></section>
<section><h2>Regras aplicadas</h2><pre>{rules}</pre><p>Validação determinística em Python e SQL. Os dados originais não foram alterados.</p></section></html>""".encode("utf-8")
