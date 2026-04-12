import psycopg2
import psycopg2.extras
import csv
import io
import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, Response

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sistema_chamados_secret_key_change_me')

DATABASE_URL = os.environ.get('DATABASE_URL', '')

STATUS_OPTIONS = ['Solicitado', 'Em Verificação', 'Em Andamento', 'Finalizado']
STATUS_COLORS = {
    'Solicitado': 'secondary',
    'Em Verificação': 'warning',
    'Em Andamento': 'primary',
    'Finalizado': 'success'
}


def get_db():
    """Retorna uma conexão com o banco PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    """Helper para executar queries e retornar resultados como dicionários."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            result = None
            if fetchone:
                result = cur.fetchone()
            elif fetchall:
                result = cur.fetchall()
            if commit:
                conn.commit()
        return result
    finally:
        conn.close()


def gerar_numero_chamado():
    ano = datetime.now().year
    row = query(
        "SELECT COUNT(*) as total FROM chamados WHERE numero_chamado LIKE %s",
        (f'CHM-{ano}-%',), fetchone=True
    )
    sequencial = (row['total'] if row else 0) + 1
    return f'CHM-{ano}-{sequencial:04d}'


def formatar_data(data_val):
    if not data_val:
        return ''
    if hasattr(data_val, 'strftime'):
        return data_val.strftime('%d/%m/%Y')
    try:
        d = datetime.strptime(str(data_val), '%Y-%m-%d')
        return d.strftime('%d/%m/%Y')
    except Exception:
        return str(data_val)


def formatar_cpf(cpf):
    cpf = ''.join(filter(str.isdigit, str(cpf or '')))
    if len(cpf) == 11:
        return f'{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}'
    return cpf


@app.route('/')
def index():
    status_filtro = request.args.get('status', '')
    busca = request.args.get('busca', '')

    sql = "SELECT * FROM chamados WHERE 1=1"
    params = []

    if status_filtro:
        sql += " AND status = %s"
        params.append(status_filtro)

    if busca:
        sql += " AND (numero_chamado ILIKE %s OR nome_solicitante ILIKE %s OR nome_candidato ILIKE %s OR cpf_candidato ILIKE %s)"
        params.extend([f'%{busca}%'] * 4)

    sql += " ORDER BY id DESC"

    chamados_raw = query(sql, params, fetchall=True) or []

    stats = {}
    for s in STATUS_OPTIONS:
        row = query("SELECT COUNT(*) as total FROM chamados WHERE status = %s", (s,), fetchone=True)
        stats[s] = row['total'] if row else 0

    chamados_list = []
    for c in chamados_raw:
        c = dict(c)
        c['data_solicitacao_fmt'] = formatar_data(c.get('data_solicitacao'))
        c['data_concurso_fmt'] = formatar_data(c.get('data_concurso'))
        c['status_color'] = STATUS_COLORS.get(c['status'], 'secondary')
        c['cpf_fmt'] = formatar_cpf(c.get('cpf_candidato', ''))
        chamados_list.append(c)

    return render_template('index.html',
                           chamados=chamados_list,
                           status_options=STATUS_OPTIONS,
                           status_filtro=status_filtro,
                           busca=busca,
                           stats=stats,
                           status_colors=STATUS_COLORS)


@app.route('/novo', methods=['GET', 'POST'])
def novo_chamado():
    if request.method == 'POST':
        nome_solicitante = request.form.get('nome_solicitante', '').strip()
        setor_cargo = request.form.get('setor_cargo', '').strip()
        nome_candidato = request.form.get('nome_candidato', '').strip()
        cpf_candidato = request.form.get('cpf_candidato', '').strip()
        numero_inscricao = request.form.get('numero_inscricao', '').strip()
        concurso_processo = request.form.get('concurso_processo', '').strip()
        data_solicitacao = request.form.get('data_solicitacao', '').strip()
        data_concurso = request.form.get('data_concurso', '').strip()
        observacoes = request.form.get('observacoes', '').strip()

        errors = []
        if not nome_solicitante: errors.append('Nome do solicitante é obrigatório.')
        if not setor_cargo: errors.append('Setor e cargo é obrigatório.')
        if not nome_candidato: errors.append('Nome do candidato é obrigatório.')
        if not cpf_candidato: errors.append('CPF do candidato é obrigatório.')
        if not numero_inscricao: errors.append('Número de inscrição é obrigatório.')
        if not concurso_processo: errors.append('Concurso e número do processo é obrigatório.')
        if not data_solicitacao: errors.append('Data da solicitação é obrigatória.')
        if len(observacoes) > 600: errors.append('Observações: máximo de 600 caracteres.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('form.html', form_data=request.form, title='Novo Chamado')

        numero_chamado = gerar_numero_chamado()
        agora = datetime.now()

        query('''
            INSERT INTO chamados (
                numero_chamado, status, nome_solicitante, setor_cargo,
                nome_candidato, cpf_candidato, numero_inscricao,
                concurso_processo, data_solicitacao, data_concurso,
                observacoes, created_at, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', (
            numero_chamado, 'Solicitado', nome_solicitante, setor_cargo,
            nome_candidato, cpf_candidato, numero_inscricao,
            concurso_processo, data_solicitacao, data_concurso or None,
            observacoes, agora, agora
        ), commit=True)

        flash(f'Chamado {numero_chamado} criado com sucesso!', 'success')
        return redirect(url_for('index'))

    hoje = date.today().strftime('%Y-%m-%d')
    return render_template('form.html', form_data={'data_solicitacao': hoje}, title='Novo Chamado')


@app.route('/chamado/<int:chamado_id>')
def ver_chamado(chamado_id):
    c = query('SELECT * FROM chamados WHERE id = %s', (chamado_id,), fetchone=True)
    if not c:
        flash('Chamado não encontrado.', 'danger')
        return redirect(url_for('index'))

    c = dict(c)
    c['data_solicitacao_fmt'] = formatar_data(c.get('data_solicitacao'))
    c['data_concurso_fmt'] = formatar_data(c.get('data_concurso'))
    c['status_color'] = STATUS_COLORS.get(c['status'], 'secondary')
    c['cpf_fmt'] = formatar_cpf(c.get('cpf_candidato', ''))
    created = c.get('created_at')
    c['created_at_fmt'] = created.strftime('%d/%m/%Y %H:%M') if hasattr(created, 'strftime') else str(created or '')

    return render_template('chamado.html',
                           chamado=c,
                           status_options=STATUS_OPTIONS,
                           status_colors=STATUS_COLORS)


@app.route('/chamado/<int:chamado_id>/editar', methods=['GET', 'POST'])
def editar_chamado(chamado_id):
    chamado = query('SELECT * FROM chamados WHERE id = %s', (chamado_id,), fetchone=True)
    if not chamado:
        flash('Chamado não encontrado.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        nome_solicitante = request.form.get('nome_solicitante', '').strip()
        setor_cargo = request.form.get('setor_cargo', '').strip()
        nome_candidato = request.form.get('nome_candidato', '').strip()
        cpf_candidato = request.form.get('cpf_candidato', '').strip()
        numero_inscricao = request.form.get('numero_inscricao', '').strip()
        concurso_processo = request.form.get('concurso_processo', '').strip()
        data_solicitacao = request.form.get('data_solicitacao', '').strip()
        data_concurso = request.form.get('data_concurso', '').strip()
        observacoes = request.form.get('observacoes', '').strip()
        status = request.form.get('status', 'Solicitado')

        errors = []
        if not nome_solicitante: errors.append('Nome do solicitante é obrigatório.')
        if not setor_cargo: errors.append('Setor e cargo é obrigatório.')
        if not nome_candidato: errors.append('Nome do candidato é obrigatório.')
        if not cpf_candidato: errors.append('CPF do candidato é obrigatório.')
        if not numero_inscricao: errors.append('Número de inscrição é obrigatório.')
        if not concurso_processo: errors.append('Concurso e número do processo é obrigatório.')
        if not data_solicitacao: errors.append('Data da solicitação é obrigatória.')
        if len(observacoes) > 600: errors.append('Observações: máximo de 600 caracteres.')
        if status not in STATUS_OPTIONS: errors.append('Status inválido.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            c = dict(chamado)
            c.update(request.form)
            return render_template('form.html', form_data=c, title='Editar Chamado',
                                   chamado_id=chamado_id, status_options=STATUS_OPTIONS,
                                   numero_chamado=chamado['numero_chamado'])

        agora = datetime.now()
        query('''
            UPDATE chamados SET
                status=%s, nome_solicitante=%s, setor_cargo=%s,
                nome_candidato=%s, cpf_candidato=%s, numero_inscricao=%s,
                concurso_processo=%s, data_solicitacao=%s, data_concurso=%s,
                observacoes=%s, updated_at=%s
            WHERE id=%s
        ''', (
            status, nome_solicitante, setor_cargo,
            nome_candidato, cpf_candidato, numero_inscricao,
            concurso_processo, data_solicitacao, data_concurso or None,
            observacoes, agora, chamado_id
        ), commit=True)

        flash('Chamado atualizado com sucesso!', 'success')
        return redirect(url_for('ver_chamado', chamado_id=chamado_id))

    c = dict(chamado)
    if c.get('data_solicitacao') and hasattr(c['data_solicitacao'], 'strftime'):
        c['data_solicitacao'] = c['data_solicitacao'].strftime('%Y-%m-%d')
    if c.get('data_concurso') and hasattr(c['data_concurso'], 'strftime'):
        c['data_concurso'] = c['data_concurso'].strftime('%Y-%m-%d')

    return render_template('form.html',
                           form_data=c,
                           title='Editar Chamado',
                           chamado_id=chamado_id,
                           status_options=STATUS_OPTIONS,
                           numero_chamado=c['numero_chamado'])


@app.route('/chamado/<int:chamado_id>/status', methods=['POST'])
def atualizar_status(chamado_id):
    novo_status = request.form.get('status')
    if novo_status not in STATUS_OPTIONS:
        flash('Status inválido.', 'danger')
        return redirect(url_for('ver_chamado', chamado_id=chamado_id))

    query('UPDATE chamados SET status=%s, updated_at=%s WHERE id=%s',
          (novo_status, datetime.now(), chamado_id), commit=True)

    flash(f'Status atualizado para "{novo_status}".', 'success')
    return redirect(url_for('ver_chamado', chamado_id=chamado_id))


@app.route('/exportar')
def exportar_csv():
    status_filtro = request.args.get('status', '')
    busca = request.args.get('busca', '')
    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')

    sql = "SELECT * FROM chamados WHERE 1=1"
    params = []

    if status_filtro:
        sql += " AND status = %s"
        params.append(status_filtro)
    if busca:
        sql += " AND (numero_chamado ILIKE %s OR nome_solicitante ILIKE %s OR nome_candidato ILIKE %s)"
        params.extend([f'%{busca}%'] * 3)
    if data_inicio:
        sql += " AND data_solicitacao >= %s"
        params.append(data_inicio)
    if data_fim:
        sql += " AND data_solicitacao <= %s"
        params.append(data_fim)

    sql += " ORDER BY id DESC"
    chamados = query(sql, params, fetchall=True) or []

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'Número do Chamado', 'Status', 'Nome do Solicitante', 'Setor e Cargo',
        'Nome do Candidato', 'CPF do Candidato', 'Número de Inscrição',
        'Concurso / Processo Judicial', 'Data da Solicitação', 'Data do Concurso',
        'Observações', 'Criado em', 'Atualizado em'
    ])
    for c in chamados:
        c = dict(c)
        writer.writerow([
            c.get('numero_chamado', ''),
            c.get('status', ''),
            c.get('nome_solicitante', ''),
            c.get('setor_cargo', ''),
            c.get('nome_candidato', ''),
            formatar_cpf(c.get('cpf_candidato', '')),
            c.get('numero_inscricao', ''),
            c.get('concurso_processo', ''),
            formatar_data(c.get('data_solicitacao')),
            formatar_data(c.get('data_concurso')),
            c.get('observacoes', ''),
            str(c.get('created_at', '')),
            str(c.get('updated_at', '')),
        ])

    output.seek(0)
    csv_data = '\ufeff' + output.getvalue()
    nome_arquivo = f'chamados_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    return Response(
        csv_data.encode('utf-8'),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={nome_arquivo}'}
    )


@app.route('/relatorios')
def relatorios():
    row = query("SELECT COUNT(*) as t FROM chamados", fetchone=True)
    total = row['t'] if row else 0

    por_status = {}
    for s in STATUS_OPTIONS:
        r = query("SELECT COUNT(*) as t FROM chamados WHERE status=%s", (s,), fetchone=True)
        por_status[s] = r['t'] if r else 0

    ultimos_raw = query("SELECT * FROM chamados ORDER BY id DESC LIMIT 10", fetchall=True) or []
    ultimos_list = []
    for c in ultimos_raw:
        c = dict(c)
        c['data_solicitacao_fmt'] = formatar_data(c.get('data_solicitacao'))
        c['status_color'] = STATUS_COLORS.get(c['status'], 'secondary')
        ultimos_list.append(c)

    return render_template('relatorios.html',
                           total=total,
                           por_status=por_status,
                           ultimos=ultimos_list,
                           status_options=STATUS_OPTIONS,
                           status_colors=STATUS_COLORS)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
