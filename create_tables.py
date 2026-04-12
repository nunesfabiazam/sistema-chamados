"""
Execute este script UMA VEZ para criar as tabelas no banco de dados Neon.

Como usar:
  1. Defina a variável de ambiente DATABASE_URL com a connection string do Neon
     Windows PowerShell:  $env:DATABASE_URL="postgresql://user:pass@host/db"
     Mac/Linux:           export DATABASE_URL="postgresql://user:pass@host/db"

  2. Execute:
     python create_tables.py
"""

import os
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL', '')

if not DATABASE_URL:
    print("ERRO: A variável de ambiente DATABASE_URL não está definida.")
    print("Defina-a antes de executar este script.")
    exit(1)

print("Conectando ao banco de dados...")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("Criando tabela 'chamados'...")
cur.execute('''
    CREATE TABLE IF NOT EXISTS chamados (
        id          SERIAL PRIMARY KEY,
        numero_chamado  VARCHAR(20)  UNIQUE NOT NULL,
        status          VARCHAR(30)  NOT NULL DEFAULT 'Solicitado',
        nome_solicitante VARCHAR(200) NOT NULL,
        setor_cargo     VARCHAR(200) NOT NULL,
        nome_candidato  VARCHAR(200) NOT NULL,
        cpf_candidato   VARCHAR(20)  NOT NULL,
        numero_inscricao VARCHAR(50) NOT NULL,
        concurso_processo VARCHAR(500) NOT NULL,
        data_solicitacao DATE        NOT NULL,
        data_concurso    DATE,
        observacoes      TEXT,
        created_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
        updated_at       TIMESTAMP   NOT NULL DEFAULT NOW()
    )
''')

conn.commit()
cur.close()
conn.close()

print("Tabela criada com sucesso!")
print("Agora você pode fazer o deploy no Vercel.")
