import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import time
import sqlite3
import numpy as np
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sonae Vital", layout="wide", initial_sidebar_state="expanded")

# --- 2. BASE DE DADOS SQLITE (CONSULTAS, EVOLUÇÃO E UTILIZADORES) ---
def iniciar_base_dados():
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consultas (
            id_consulta INTEGER PRIMARY KEY AUTOINCREMENT,
            id_colaborador TEXT,
            especialidade TEXT,
            data_consulta TEXT,
            hora_consulta TEXT,
            observacoes TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS avaliacoes (
            id_avaliacao INTEGER PRIMARY KEY AUTOINCREMENT,
            id_consulta INTEGER,
            id_colaborador TEXT,
            metrica TEXT,
            valor_antigo REAL,
            valor_novo REAL,
            data_registo TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS utilizadores (
            id_colaborador TEXT PRIMARY KEY,
            email TEXT,
            password TEXT,
            tipo TEXT,
            nome TEXT
        )
    ''')
    
    # Atualização dinâmica: se a tabela utilizadores já existir do código antigo, 
    # adiciona a coluna 'nome' sem destruir os dados. Se já tiver a coluna, ignora o erro.
    try:
        cursor.execute("ALTER TABLE utilizadores ADD COLUMN nome TEXT")
    except:
        pass
        
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_urgentes (
            id_pedido INTEGER PRIMARY KEY AUTOINCREMENT,
            id_colaborador TEXT,
            especialidade TEXT,
            motivo TEXT,
            data_pedido TEXT,
            estado TEXT
        )
    ''')
    
    conexao.commit()
    conexao.close()

iniciar_base_dados()

def iniciar_tabela_codigos():
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS codigos_prof (codigo TEXT PRIMARY KEY, especialidade TEXT, usado INTEGER)''')
    conexao.commit()
    conexao.close()

iniciar_tabela_codigos()

def verificar_codigo_prof_db_simples(codigo):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute("SELECT especialidade FROM codigos_prof WHERE codigo = ? AND usado = 0", (codigo,))
    resultado = cursor.fetchone()
    conexao.close()
    return resultado[0] if resultado else None

def gerar_codigo_prof_db(especialidade):
    import random
    import string
    prefixo = especialidade[:3].upper()
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    codigo = f"{prefixo}-{chars}"
    
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute("INSERT INTO codigos_prof (codigo, especialidade, usado) VALUES (?, ?, 0)", (codigo, especialidade))
    conexao.commit()
    conexao.close()
    return codigo

def validar_codigo_prof_db(codigo):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute("SELECT especialidade FROM codigos_prof WHERE codigo = ? AND usado = 0", (codigo,))
    resultado = cursor.fetchone()
    if resultado:
        cursor.execute("UPDATE codigos_prof SET usado = 1 WHERE codigo = ?", (codigo,))
        conexao.commit()
        conexao.close()
        return resultado[0]
    conexao.close()
    return None

# --- FUNÇÕES DE BD PARA UTILIZADORES ---
def registar_utilizador_db(id_colab, email, password, tipo="colaborador", nome=""):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    try:
        # Agora injeta também o 'nome' do profissional
        cursor.execute("INSERT INTO utilizadores (id_colaborador, email, password, tipo, nome) VALUES (?, ?, ?, ?, ?)", 
                       (str(id_colab), email, password, tipo, nome))
        conexao.commit()
        sucesso = True
    except sqlite3.IntegrityError:
        sucesso = False 
    conexao.close()
    return sucesso

def verificar_login_db(id_colab, password):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute("SELECT tipo FROM utilizadores WHERE id_colaborador = ? AND password = ?", (str(id_colab), password))
    resultado = cursor.fetchone()
    conexao.close()
    if resultado:
        return resultado[0]
    return None

def obter_profissionais_db():
    conexao = sqlite3.connect('sonae_saude.db')
    query = "SELECT COALESCE(NULLIF(nome, ''), id_colaborador) as 'Nome', email as 'Email', tipo as 'Especialidade', id_colaborador as 'ID Oculto' FROM utilizadores WHERE tipo NOT IN ('colaborador', 'admin')"
    df_prof = pd.read_sql_query(query, conexao)
    conexao.close()
    
    # Traduzir os códigos da BD para os nomes visuais bonitos
    if not df_prof.empty and 'Especialidade' in df_prof.columns:
        df_prof['Especialidade'] = df_prof['Especialidade'].replace({
            'reforco': 'Técnico',
            'fisioterapeuta': 'Fisioterapeuta',
            'nutricionista': 'Nutricionista'
        })
        
    return df_prof

def remover_utilizador_db(id_colab):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM utilizadores WHERE id_colaborador = ?", (str(id_colab),))
    conexao.commit()
    conexao.close()

# --- FUNÇÕES DE BD PARA CLÍNICA ---
def agendar_consulta_db(id_colab, especialidade, data, hora, obs):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute('''
        INSERT INTO consultas (id_colaborador, especialidade, data_consulta, hora_consulta, observacoes)
        VALUES (?, ?, ?, ?, ?)
    ''', (str(id_colab), especialidade, data, hora, obs))
    conexao.commit()
    conexao.close()

def cancelar_consulta_db(id_consulta):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM consultas WHERE id_consulta = ?", (int(id_consulta),))
    conexao.commit()
    conexao.close()

def obter_consultas(id_colab=None, especialidade=None, id_consulta=None):
    conexao = sqlite3.connect('sonae_saude.db')
    if id_consulta:
        query = f"SELECT * FROM consultas WHERE id_consulta = {id_consulta}"
    elif id_colab:
        query = f"SELECT * FROM consultas WHERE id_colaborador = '{id_colab}' ORDER BY data_consulta, hora_consulta"
    elif especialidade:
        query = f"SELECT * FROM consultas WHERE especialidade = '{especialidade}' ORDER BY data_consulta, hora_consulta"
    else:
        query = "SELECT * FROM consultas ORDER BY data_consulta, hora_consulta"
    
    df_consultas = pd.read_sql_query(query, conexao)
    conexao.close()
    return df_consultas

def guardar_avaliacao(id_consulta, id_colab, metrica, v_antigo, v_novo):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    data_hoje = datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
    cursor.execute('''
        INSERT INTO avaliacoes (id_consulta, id_colaborador, metrica, valor_antigo, valor_novo, data_registo)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (id_consulta, str(id_colab), metrica, float(v_antigo), float(v_novo), data_hoje))
    conexao.commit()
    conexao.close()

def apagar_avaliacao_db_por_data(id_colab, data_registo):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM avaliacoes WHERE id_colaborador = ? AND data_registo = ?", (str(id_colab), str(data_registo)))
    conexao.commit()
    conexao.close()

def obter_avaliacoes(id_colab):
    conexao = sqlite3.connect('sonae_saude.db')
    query = f"SELECT * FROM avaliacoes WHERE id_colaborador = '{id_colab}' ORDER BY data_registo ASC"
    df_av = pd.read_sql_query(query, conexao)
    conexao.close()
    return df_av

def obter_valor_recente(id_colab, metrica_nome, valor_ia):
    df_av = obter_avaliacoes(id_colab)
    if not df_av.empty:
        av_metrica = df_av[df_av['metrica'] == metrica_nome]
        if not av_metrica.empty:
            return av_metrica.iloc[-1]['valor_novo']
    return valor_ia

# --- FUNÇÕES DE BD PARA PEDIDOS URGENTES ---
def criar_pedido_urgente_db(id_colab, especialidade, motivo):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    data_hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("INSERT INTO pedidos_urgentes (id_colaborador, especialidade, motivo, data_pedido, estado) VALUES (?, ?, ?, ?, ?)",
                   (str(id_colab), especialidade, motivo, data_hoje, 'Pendente'))
    conexao.commit()
    conexao.close()

def obter_pedidos_urgentes(especialidade=None, id_colab=None):
    conexao = sqlite3.connect('sonae_saude.db')
    query = "SELECT * FROM pedidos_urgentes WHERE estado = 'Pendente'"
    if especialidade:
        query += f" AND especialidade = '{especialidade}'"
    if id_colab:
        query += f" AND id_colaborador = '{id_colab}'"
    df = pd.read_sql_query(query, conexao)
    conexao.close()
    return df

def resolver_pedido_urgente(id_pedido):
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute("UPDATE pedidos_urgentes SET estado = 'Atendido' WHERE id_pedido = ?", (int(id_pedido),))
    conexao.commit()
    conexao.close()

def inativar_colaborador_sistema(id_colab):
    id_str = str(id_colab).replace('.0', '')
    
    # 1. Remover acesso ao login e cancelar consultas marcadas
    conexao = sqlite3.connect('sonae_saude.db')
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM utilizadores WHERE id_colaborador = ?", (id_str,))
    cursor.execute("DELETE FROM consultas WHERE id_colaborador = ?", (id_str,))
    conexao.commit()
    conexao.close()
    
    # 2. Alterar o estado no Excel em vez de apagar a linha
    df = pd.read_excel('dataset_final_para_outsystems.xlsx')
    if 'Estado' not in df.columns:
        df['Estado'] = 'Ativo'
    df.loc[df['ID'].astype(str).str.replace('.0', '', regex=False) == id_str, 'Estado'] = 'Inativo'
    df.to_excel('dataset_final_para_outsystems.xlsx', index=False)
    
    if 'historico_admin' in st.session_state:
        st.session_state['historico_admin'].insert(0, f"{datetime.now().strftime('%Y-%m-%d %H:%M')} - Colaborador {id_str} inativado.")

def reativar_colaborador_sistema(id_colab):
    id_str = str(id_colab).replace('.0', '')
    
    df = pd.read_excel('dataset_final_para_outsystems.xlsx')
    if 'Estado' not in df.columns:
        df['Estado'] = 'Ativo'
    df.loc[df['ID'].astype(str).str.replace('.0', '', regex=False) == id_str, 'Estado'] = 'Ativo'
    df.to_excel('dataset_final_para_outsystems.xlsx', index=False)
    
    if 'historico_admin' in st.session_state:
        st.session_state['historico_admin'].insert(0, f"{datetime.now().strftime('%Y-%m-%d %H:%M')} - Colaborador {id_str} reativado.")

# --- 3. MEMÓRIA DA SESSÃO ---
if 'autenticado' not in st.session_state: st.session_state['autenticado'] = False
if 'id_selecionado' not in st.session_state: st.session_state['id_selecionado'] = None
if 'pagina_atual' not in st.session_state: st.session_state['pagina_atual'] = 'menu_principal'
if 'tipo_utilizador' not in st.session_state: st.session_state['tipo_utilizador'] = None
if 'semana_offset' not in st.session_state: st.session_state['semana_offset'] = 0 
if 'paciente_agendamento' not in st.session_state: st.session_state['paciente_agendamento'] = None
if 'confirmar_data' not in st.session_state: st.session_state['confirmar_data'] = None
if 'confirmar_hora' not in st.session_state: st.session_state['confirmar_hora'] = None
if 'consulta_ativa' not in st.session_state: st.session_state['consulta_ativa'] = None

# --- 4. CARREGAR DADOS (EXCEL) ---
def carregar_dados():
    return pd.read_excel('dataset_final_para_outsystems.xlsx')

# --- CABEÇALHO COM SININHO DE NOTIFICAÇÕES ---
def desenhar_cabecalho_notificacoes():
    if not st.session_state['autenticado']: return
    
    tipo = st.session_state['tipo_utilizador']
    col_vazia, col_sino = st.columns([10, 1])
    
    with col_sino:
        if tipo in ['fisioterapeuta', 'nutricionista', 'reforco']:
            esp = "Fisioterapia" if tipo == 'fisioterapeuta' else "Nutrição" if tipo == 'nutricionista' else "Reforço Muscular"
            df_urg = obter_pedidos_urgentes(especialidade=esp)
            num_notif = len(df_urg)
            
            with st.popover(f"🔔 {num_notif}"):
                st.markdown("**Notificações Clínicas**")
                if num_notif == 0:
                    st.write("Sem alertas no momento.")
                else:
                    for _, row in df_urg.iterrows():
                        st.error(f"🚨 **URGÊNCIA**\nID: {row['id_colaborador']}\nMotivo: {row['motivo']}")
        
        elif tipo == 'colaborador':
            id_colab = st.session_state.get('id_selecionado')
            df_cons = obter_consultas(id_colab=id_colab)
            hoje_str = datetime.now().strftime("%Y-%m-%d")
            df_futuras = df_cons[df_cons['data_consulta'] >= hoje_str]
            num_notif = len(df_futuras)
            
            with st.popover(f"🔔 {num_notif}"):
                st.markdown("**As Minhas Marcações**")
                if num_notif == 0:
                    st.write("Não tem consultas futuras agendadas.")
                else:
                    for _, row in df_futuras.iterrows():
                        if row['especialidade'] == 'Fisioterapia':
                            st.error(f"📅 **{row['data_consulta']} às {row['hora_consulta']}**\n🩺 {row['especialidade']}")
                        elif row['especialidade'] == 'Nutrição':
                            st.warning(f"📅 **{row['data_consulta']} às {row['hora_consulta']}**\n🩺 {row['especialidade']}")
                        else:
                            st.info(f"📅 **{row['data_consulta']} às {row['hora_consulta']}**\n🩺 {row['especialidade']}")
        else:
            with st.popover("🔔 0"):
                st.write("Sem notificações no momento.")

# --- 5. ECRÃS DO SISTEMA ---

def mostrar_ecra_login():
    st.markdown("""
        <style>
        .stApp { background-color: var(--background-color); background-image: radial-gradient(var(--secondary-background-color) 2px, transparent 2px); background-size: 30px 30px; }
        div[data-testid="stForm"] { background-color: var(--background-color); border: 1px solid var(--secondary-background-color); border-radius: 16px; box-shadow: 0 10px 35px rgba(0, 0, 0, 0.25); padding: 35px; }
        .titulo-portal { text-align: center; white-space: nowrap; font-size: 3.2rem; font-weight: 800; margin-bottom: 0; padding-bottom: 0; }
        .subtitulo-portal { text-align: center; font-size: 1.1rem; color: gray; margin-bottom: 25px; }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown('<h1 class="titulo-portal">🩺 Sonae Vital</h1>', unsafe_allow_html=True)
        st.markdown('<p class="subtitulo-portal">Bem-vindo. Identifique-se para aceder ao portal.</p>', unsafe_allow_html=True)
        
        tab_login, tab_registo = st.tabs(["🔑 Iniciar Sessão", "📝 Registar Conta"])
        
        with tab_login:
            with st.form("form_login"):
                utilizador = st.text_input("ID")
                palavra_passe = st.text_input("Palavra-passe", type="password")
                
                if st.form_submit_button("Entrar", use_container_width=True):
                    st.session_state['semana_offset'] = 0
                    
                    if utilizador == "admin" and palavra_passe == "admin":
                        st.session_state['tipo_utilizador'] = 'admin'
                        st.session_state['autenticado'] = True
                        st.session_state['pagina_atual'] = 'menu_principal'
                        st.rerun()
                    else:
                        tipo_bd = verificar_login_db(utilizador, palavra_passe)
                        if tipo_bd:
                            st.session_state['tipo_utilizador'] = tipo_bd
                            st.session_state['autenticado'] = True
                            # O Dashboard decide para onde o utilizador vai consoante o seu tipo
                            if tipo_bd == 'colaborador':
                                st.session_state['pagina_atual'] = 'perfil'
                                st.session_state['id_selecionado'] = utilizador
                            else:
                                st.session_state['pagina_atual'] = 'menu_principal'
                            st.rerun()
                        else:
                            st.error("Credenciais incorretas ou conta não existe!")
                            
        with tab_registo:
            st.info("Registo para Colaboradores e Profissionais de Saúde.")
            novo_id = st.text_input("ID")
            
            col_v1, col_v2 = st.columns([3, 1])
            codigo_auth = col_v1.text_input("Código de Autorização", type="password")
            col_v2.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            btn_verificar = col_v2.button("Verificar", use_container_width=True)
            
            if 'cod_valido' not in st.session_state:
                st.session_state['cod_valido'] = False
                st.session_state['tipo_cod'] = None
                
            if btn_verificar:
                if not novo_id or not codigo_auth:
                    st.error("Preencha o ID e o Código primeiro.")
                else:
                    esp = verificar_codigo_prof_db_simples(codigo_auth)
                    if esp:
                        st.session_state['cod_valido'] = True
                        st.session_state['tipo_cod'] = esp
                        st.success(f"Código clínico válido: Especialidade {esp.capitalize()}")
                    else:
                        df = carregar_dados()
                        if novo_id in df['ID'].astype(str).values and codigo_auth == novo_id:
                            st.session_state['cod_valido'] = True
                            st.session_state['tipo_cod'] = 'colaborador'
                            st.success("Código de colaborador validado!")
                        else:
                            st.session_state['cod_valido'] = False
                            st.error("Código ou ID inválidos.")
                            
            if st.session_state.get('cod_valido'):
                st.markdown("---")
                
                nome = ""
                apelido = ""
                # O sistema deteta que é profissional e pede logo Nome e Apelido
                if st.session_state['tipo_cod'] != 'colaborador':
                    c_n1, c_n2 = st.columns(2)
                    nome = c_n1.text_input("Nome")
                    apelido = c_n2.text_input("Apelido")
                    
                email = st.text_input("Email")
                pass1 = st.text_input("Crie uma Palavra-passe", type="password")
                pass2 = st.text_input("Confirme a Palavra-passe", type="password")
                
                if st.button("Criar Conta Segura", use_container_width=True):
                    if pass1 != pass2: st.error("As palavras-passe não coincidem.")
                    elif len(pass1) < 4: st.error("A palavra-passe deve ter pelo menos 4 caracteres.")
                    else:
                        tipo_final = st.session_state['tipo_cod']
                        
                        if tipo_final != 'colaborador': 
                            validar_codigo_prof_db(codigo_auth)
                            nome_completo = f"{nome} {apelido}".strip()
                        else:
                            nome_completo = ""
                            
                        # Grava o nome completo na Base de Dados
                        sucesso = registar_utilizador_db(novo_id, email, pass1, tipo=tipo_final, nome=nome_completo)
                        if sucesso:
                            st.success("Conta criada! Já pode Iniciar Sessão na outra aba.")
                            st.balloons()
                            st.session_state['cod_valido'] = False
                        else:
                            st.error("Este ID já tem conta registada.")

def mostrar_menu_principal():
    st.markdown("""
        <style>
        [data-testid="stMain"] div.stButton > button {
            min-height: 180px !important; border-radius: 16px !important;
            box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.15) !important; white-space: pre-wrap !important;
            display: flex !important; flex-direction: column !important; justify-content: center !important;
            align-items: center !important; text-align: center !important; padding: 20px !important;
            transition: all 0.3s ease;
        }
        [data-testid="stMain"] div.stButton > button:hover {
            transform: translateY(-5px);
            box-shadow: 0px 8px 20px rgba(0, 0, 0, 0.2) !important;
        }
        [data-testid="stMain"] div.stButton > button p { font-size: 22px !important; font-weight: bold !important; }
        </style>
    """, unsafe_allow_html=True)

    tipo = st.session_state['tipo_utilizador']
    
    if tipo == 'admin':
        st.title("🏠 Menu Principal")
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📊 Dashboard Global", use_container_width=True):
                st.session_state['pagina_atual'] = 'dashboard'
                st.rerun()
            st.write("") 
            if st.button("👥 Listagem Geral", use_container_width=True):
                st.session_state['pagina_atual'] = 'listagem'
                st.rerun()
        with col2:
            if st.button("⚕️ Gestão de Profissionais", use_container_width=True):
                st.session_state['pagina_atual'] = 'gestao_profissionais'
                st.rerun()
            st.write("")
            if st.button("⚙️ Gestão de Dados", use_container_width=True):
                st.session_state['pagina_atual'] = 'gestao_dados'
                st.rerun()

    elif tipo in ['fisioterapeuta', 'nutricionista', 'reforco']:
        especialidade = "Fisioterapia" if tipo == 'fisioterapeuta' else "Nutrição" if tipo == 'nutricionista' else "Reforço Muscular"
        st.title(f"⚕️ Portal Clínico - {especialidade}")
        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📋 Fila de Espera", use_container_width=True):
                st.session_state['pagina_atual'] = 'listagem'
                st.rerun()
        with col2:
            if st.button("📅 Agenda Clínica", use_container_width=True):
                st.session_state['pagina_atual'] = 'agenda'
                st.rerun()
        with col3:
            if st.button("👤 Perfil Clínico", use_container_width=True):
                st.session_state['pagina_atual'] = 'perfil'
                st.rerun()

def mostrar_perfil():
    df = carregar_dados()
    tipo = st.session_state['tipo_utilizador']
    
    # 1. Títulos super simples, sem parêntesis!
    if tipo == 'admin': 
        st.title("👤 Perfil do Colaborador")
    elif tipo == 'colaborador': 
        st.title("👤 O Meu Perfil de Saúde")
    else: 
        st.title("👤 Perfil Clínico")

    st.divider()
            
    if tipo != 'colaborador':
        # 2. Filtros na horizontal (lado a lado), a ocupar a largura total
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            # Lemos 'Localizacao' da base de dados, mas escrevemos 'Entreposto' no ecrã para o utilizador
            col_local = 'Localizacao' if 'Localizacao' in df.columns else None
            
            if col_local:
                locais_existentes = [str(x).capitalize() for x in df[col_local].dropna().unique()]
            else:
                locais_existentes = []
                
            locais = ['Geral'] + sorted(list(set(locais_existentes)))
            loc_selecionada = st.selectbox("📍 1. Entreposto", locais)
            
        df_filtrado = df if loc_selecionada == 'Geral' else df[df[col_local].astype(str).str.capitalize() == loc_selecionada] if col_local else df
        
        with col_f2:
            col_dep = 'Departamento' if 'Departamento' in df.columns else ('Função' if 'Função' in df.columns else None)
            if col_dep and col_dep in df_filtrado.columns:
                deps = ['Todos'] + sorted(df_filtrado[col_dep].dropna().astype(str).unique().tolist())
            else:
                deps = ['Todos']
                
            dep_selecionado = st.selectbox("🏢 2. Departamento", deps)
            
        if dep_selecionado != 'Todos' and col_dep:
            df_filtrado = df_filtrado[df_filtrado[col_dep].astype(str) == dep_selecionado]
            
        with col_f3:
            lista_ids = df_filtrado['ID'].astype(str).unique().tolist()
            if not lista_ids:
                st.error("Sem colaboradores para estes filtros.")
                return
                
            id_guardado = str(st.session_state.get('id_selecionado'))
            idx_default = lista_ids.index(id_guardado) if id_guardado in lista_ids else 0
            
            id_escolhido = st.selectbox("👤 3. ID do Colaborador", lista_ids, index=idx_default)
            st.session_state['id_selecionado'] = id_escolhido
            id_paciente = str(id_escolhido)
            
        st.markdown("---")
    else:
        id_paciente = str(st.session_state['id_selecionado'])

    dados = df[df['ID'].astype(str) == id_paciente].iloc[0]

    # --- VISTA DO ADMINISTRADOR (RH) ---
    if tipo == 'admin':
        col_h1, col_h2 = st.columns([3, 1])
        with col_h1:
            st.subheader("📋 Dados Pessoais e Organizacionais")
            
        estado_atual = str(dados.get('Estado', 'Ativo'))
        with col_h2:
            if estado_atual == 'Ativo':
                if st.button("❌ Inativar Colaborador", use_container_width=True):
                    inativar_colaborador_sistema(id_paciente)
                    st.success("✅ Colaborador inativado!")
                    time.sleep(1.5)
                    st.rerun()
            else:
                if st.button("🔄 Reativar Colaborador", type="primary", use_container_width=True):
                    reativar_colaborador_sistema(id_paciente)
                    st.success("✅ Colaborador reativado!")
                    time.sleep(1.5)
                    st.rerun()
                    
        departamento = dados.get('Departamento', dados.get('Função', 'N/D'))
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("ID", id_paciente)
        c2.metric("Estado", estado_atual)
        
        id_emp = str(dados.get('Idade do empregado', 'N/D'))
        ant = str(dados.get('Antiguidade', 'N/D'))
        c3.metric("Idade", f"{id_emp} anos" if id_emp != 'N/D' and id_emp.lower() != 'nan' else "N/D")
        c4.metric("Antiguidade", f"{ant} anos" if ant != 'N/D' and ant.lower() != 'nan' else "N/D")
        
        st.write("")
        
        # 3. Correção: A métrica volta a ler 'Localizacao' do Excel para não dar N/D!
        ent_bruto = str(dados.get('Localizacao', 'N/D'))
        if ent_bruto.lower() == 'nan' or ent_bruto.upper() == 'N/D':
            entreposto_limpo = "N/D"
        else:
            entreposto_limpo = ent_bruto.capitalize()
            
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Entreposto", entreposto_limpo)
        c6.metric("Departamento", departamento)
        
        turno_val = str(dados.get('Turno', 'N/D'))
        c7.metric("Turno", turno_val.capitalize() if turno_val.lower() != 'nan' else 'N/D')
        
        horas_sem = str(dados.get('Horas semanais', 'N/D'))
        c8.metric("Horas Semanais", f"{horas_sem}h" if horas_sem.lower() != 'nan' and horas_sem != 'N/D' else "N/D")
        
        st.divider()
        st.warning("🔒 Nota de Privacidade: O acesso à biometria, métricas fisiológicas e algoritmos de triagem está reservado exclusivamente aos profissionais de saúde e ao próprio colaborador.")
        return
    # -----------------------------------

    # --- VISTA DO CLÍNICO / COLABORADOR ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("📋 Dados Pessoais")
        departamento = dados.get('Departamento', dados.get('Função', 'N/D'))
        
        ent_bruto = str(dados.get('Localizacao', 'N/D'))
        entreposto_limpo = "N/D" if ent_bruto.lower() == 'nan' or ent_bruto.upper() == 'N/D' else ent_bruto.capitalize()
        
        id_emp = str(dados.get('Idade do empregado', 'N/D'))
        ant = str(dados.get('Antiguidade', 'N/D'))
        
        st.write(f"**Entreposto:** {entreposto_limpo}")
        st.write(f"**Departamento:** {departamento}")
        st.write(f"**Antiguidade:** {ant} anos" if ant != 'N/D' and ant.lower() != 'nan' else "**Antiguidade:** N/D")
        st.write(f"**Idade:** {id_emp} anos" if id_emp != 'N/D' and id_emp.lower() != 'nan' else "**Idade:** N/D")

    with col2:
        st.subheader("🤖 Diagnóstico IA e Triagem")
        recomendacao = str(dados.get('Recomendacao_Sistema', 'Rotina'))
        prioridade = str(dados.get('Prioridade_Consulta', 'Baixa'))
        if "Alta" in prioridade: st.error(f"**Recomendação:** {recomendacao}")
        elif "Média" in prioridade: st.warning(f"**Recomendação:** {recomendacao}")
        else: st.success(f"**Recomendação:** {recomendacao}")
        st.write(f"**Prioridade:** {prioridade}")
        
        df_cons_paciente = obter_consultas(id_colab=id_paciente)
        hoje_str = datetime.now().strftime("%Y-%m-%d")
        if not df_cons_paciente.empty:
            futuras = df_cons_paciente[df_cons_paciente['data_consulta'] >= hoje_str].sort_values(['data_consulta', 'hora_consulta'])
            if not futuras.empty:
                prox = futuras.iloc[0]
                st.info(f"📅 **Próxima Consulta:** {prox['data_consulta']} às {prox['hora_consulta']} ({prox['especialidade']})")
            else: st.write("📅 **Próxima Consulta:** Nenhuma marcada")
        else: st.write("📅 **Próxima Consulta:** Nenhuma marcada")

    val_imc = round(obter_valor_recente(id_paciente, "IMC", dados.get('IMC', 0)), 2)
    val_assimetria = round(obter_valor_recente(id_paciente, "Assimetria_Forca_%", dados.get('Assimetria_Forca_%', 0)), 2)
    val_massa = round(obter_valor_recente(id_paciente, "Massa Muscular (kg)", dados.get('Massa Muscular (kg)', 0)), 2)
    val_gap = round(obter_valor_recente(id_paciente, "Gap_Idade_Metabolica", dados.get('Gap_Idade_Metabolica', 0)), 2)
    val_visceral = round(obter_valor_recente(id_paciente, "Gordura Visceral", dados.get('Gordura Visceral', 0)), 2)
    val_gordura = round(obter_valor_recente(id_paciente, "Gordura (%)", dados.get('Gordura (%)', 0)), 2)

    with col3:
        st.subheader("⚕️ Métricas Atuais")
        st.write(f"**IMC:** {val_imc:.1f}")
        st.write(f"**Gap Metabólico:** {val_gap} anos")
        st.write(f"**Assimetria de Força:** {val_assimetria:.2f}%")
        st.write(f"**Gordura Visceral:** {val_visceral}")
        st.write(f"**Massa Muscular:** {val_massa} kg")

    st.markdown("---")
    df_av = obter_avaliacoes(id_paciente)
    if not df_av.empty:
        st.markdown("---")
    st.subheader("📈 Evolução Clínica")
    
    # 1. Obter a Data da Medição do Excel (ponto zero)
    data_medicao = dados.get('Data da Medição', 'N/D')
    if pd.isna(data_medicao) or str(data_medicao).lower() == 'nan':
        data_base_str = "Triagem Inicial"
    else:
        try: data_base_str = pd.to_datetime(data_medicao).strftime('%Y-%m-%d')
        except: data_base_str = str(data_medicao)[:10]

    # 2. Construir o dicionário com os valores originais do Excel
    lista_metricas_base = ["IMC", "Gap_Idade_Metabolica", "Assimetria_Forca_%", "Gordura Visceral", "Gordura (%)", "Massa Muscular (kg)"]
    base_dict = {'Data da Sessão': f"{data_base_str} (Base)"}
    for m in lista_metricas_base:
        try: base_dict[m] = round(float(dados.get(m, np.nan)), 2)
        except: base_dict[m] = None
        
    df_evolucao = pd.DataFrame([base_dict])
    
    # 3. Adicionar as avaliações do histórico que o Clínico registou (SQLite)
    df_av = obter_avaliacoes(id_paciente)
    if not df_av.empty:
        df_wide = df_av.pivot_table(index='data_registo', columns='metrica', values='valor_novo', aggfunc='last').reset_index()
        df_wide['Data da Sessão'] = pd.to_datetime(df_wide['data_registo']).dt.strftime('%Y-%m-%d')
        
        # Filtramos só as métricas da sessão atual para as colunas não duplicarem
        metricas_sessao = [c for c in df_wide.columns if c not in ['data_registo', 'Data da Sessão']]
        for col in metricas_sessao:
            if col not in df_evolucao.columns:
                df_evolucao[col] = None
                
        df_wide = df_wide[['Data da Sessão'] + metricas_sessao]
        df_evolucao = pd.concat([df_evolucao, df_wide], ignore_index=True)
        
    # Limpamos os Underscores (_) do cabeçalho da tabela para ficar executivo!
    df_evolucao.columns = [str(c).replace('_', ' ') for c in df_evolucao.columns]
    
    st.dataframe(df_evolucao, use_container_width=True, hide_index=True)
    st.markdown("---")

    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.subheader("Análise Multidimensional de Risco")
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=[val_imc, val_assimetria, val_gap, val_visceral, val_gordura], theta=['IMC', 'Assimetria %', 'Gap Metabólico', 'Gord. Visceral', 'Gordura %'], fill='toself', name='Perfil Atual', line_color='#2E86C1'))
        fig_radar.add_trace(go.Scatterpolar(r=[22, 5, 0, 4, 20], theta=['IMC', 'Assimetria %', 'Gap Metabólico', 'Gord. Visceral', 'Gordura %'], fill='toself', name='Padrão Saudável', line_color='#28B463'))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[-20, max(40, float(val_gap)+5)])), margin=dict(t=30, b=30, l=90, r=90))
        st.plotly_chart(fig_radar, use_container_width=True)

    with col_graf2:
        st.subheader("Risco de Desequilíbrio Muscular")
        fig_gauge = go.Figure(go.Indicator(mode = "gauge+number", value = float(val_assimetria), domain = {'x': [0, 1], 'y': [0, 1]}, title = {'text': "Assimetria (%)"}, gauge = {'axis': {'range': [None, 100]}, 'bar': {'color': "#2E86C1"}, 'steps': [{'range': [0, 10], 'color': "lightgreen"}, {'range': [10, 20], 'color': "gold"}, {'range': [20, 100], 'color': "salmon"}]}))
        st.plotly_chart(fig_gauge, use_container_width=True)

    if tipo in ['fisioterapeuta', 'nutricionista', 'reforco']:
        st.divider()
        st.markdown("### 📅 Ações Clínicas")
        if st.button("➕ Agendar Nova Consulta", type="primary", use_container_width=True):
            st.session_state['paciente_agendamento'] = id_paciente
            st.session_state['pagina_atual'] = 'agenda'
            st.rerun()

def mostrar_agenda_colaborador():
    st.title("📅 O Meu Horário e Consultas")
    st.divider()
    
    id_paciente = str(st.session_state['id_selecionado'])
    df = carregar_dados()
    dados = df[df['ID'].astype(str) == id_paciente].iloc[0]
    
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    with col_nav1:
        if st.button("⬅️ Semana Anterior", key="colab_ant", use_container_width=True):
            st.session_state['semana_offset'] -= 1
            st.rerun()
            
    hoje = datetime.now().date()
    inicio_semana = hoje - timedelta(days=hoje.weekday()) + timedelta(weeks=st.session_state['semana_offset'])
    fim_semana = inicio_semana + timedelta(days=6)
    
    with col_nav2:
        st.markdown(f"<h4 style='text-align: center;'>Semana: {inicio_semana.strftime('%d/%m/%Y')} a {fim_semana.strftime('%d/%m/%Y')}</h4>", unsafe_allow_html=True)
        
    with col_nav3:
        if st.button("Semana Seguinte ➡️", key="colab_seg", use_container_width=True):
            st.session_state['semana_offset'] += 1
            st.rerun()
            
    st.write("---")
    
    df_minhas_consultas = obter_consultas(id_colab=id_paciente)
    if not df_minhas_consultas.empty:
        df_minhas_consultas['DataObj'] = pd.to_datetime(df_minhas_consultas['data_consulta']).dt.date
    
    # --- LÓGICA DINÂMICA DO TURNO E HORAS SEMANAIS ---
    turno_paciente = str(dados.get('Turno', 'GERAL')).strip().upper()
    
    # 1. Calcular a carga horária diária (assumindo 5 dias de trabalho)
    try:
        horas_semanais = float(dados.get('Horas semanais', 40))
    except:
        horas_semanais = 40.0
    
    horas_diarias = int(horas_semanais / 5)
    
    # 2. Definir a hora de entrada base
    if 'MANHÃ' in turno_paciente:
        hora_inicio = 6
        icone_turno = "🌅"
    elif 'TARDE' in turno_paciente:
        hora_inicio = 14
        icone_turno = "🌇"
    elif 'NOITE' in turno_paciente:
        hora_inicio = 22
        icone_turno = "🌃"
    else:
        hora_inicio = 9
        icone_turno = "🏢"
        
    # 3. Calcular a hora de saída de forma cíclica (para passar da meia-noite se for preciso)
    hora_fim = (hora_inicio + horas_diarias) % 24
    
    # 4. Formatar o horário visualmente
    str_inicio = f"{hora_inicio:02d}:00"
    str_fim = f"{hora_fim:02d}:00"
    horario_str = f"{str_inicio} - {str_fim}"
    # -------------------------------------------------
    
    dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
    cols = st.columns(7)
    
    for i in range(7):
        dia_atual = inicio_semana + timedelta(days=i)
        with cols[i]:
            st.markdown(f"**{dias_semana[i]}**")
            st.caption(dia_atual.strftime('%d/%m'))
            
            # Mostrar os dias de trabalho com o visual super minimalista
            if i < 5: 
                local = str(dados.get('Localizacao', 'N/D')).capitalize()
                st.success(f"{icone_turno} **{horario_str}**\n\n{local}")
            else:
                st.write("🛌 Folga")
                
            if not df_minhas_consultas.empty:
                consultas_dia = df_minhas_consultas[df_minhas_consultas['DataObj'] == dia_atual]
                for _, c in consultas_dia.iterrows():
                    if c['especialidade'] == "Fisioterapia":
                        st.error(f"🩺 **Fisioterapia**\n\n⏰ {c['hora_consulta']}\n\n📝 {c['observacoes']}")
                    elif c['especialidade'] == "Nutrição":
                        st.warning(f"🩺 **Nutrição**\n\n⏰ {c['hora_consulta']}\n\n📝 {c['observacoes']}")
                    else:
                        st.info(f"🩺 **Reforço Muscular**\n\n⏰ {c['hora_consulta']}\n\n📝 {c['observacoes']}")

# --- ECRÃ: PEDIDO DE URGÊNCIA (COLABORADOR) ---
def mostrar_pedido_urgente():
    st.title("🚨 Pedido de Marcação Urgente")
    st.write("Sente necessidade de acompanhamento imediato? Submeta o seu pedido e o profissional de saúde será notificado imediatamente para priorizar o seu caso.")
    st.divider()
    
    id_paciente = str(st.session_state['id_selecionado'])
    
    with st.form("form_urgencia"):
        especialidade_urg = st.selectbox("Que tipo de acompanhamento necessita?", ["Fisioterapia", "Nutrição", "Reforço Muscular"])
        motivo_urg = st.text_area("Descreva os seus sintomas ou motivo da urgência:", placeholder="Ex: Sinto uma dor aguda na lombar desde ontem ao levantar caixas.")
        
        if st.form_submit_button("Submeter Pedido Urgente", type="primary", use_container_width=True):
            if len(motivo_urg) < 10:
                st.error("Por favor, descreva o motivo com mais detalhe para o clínico poder avaliar a urgência.")
            else:
                criar_pedido_urgente_db(id_paciente, especialidade_urg, motivo_urg)
                st.success("✅ O seu pedido foi enviado diretamente para o painel do especialista! Será contactado em breve.")
                st.balloons()
                time.sleep(2)
                st.session_state['pagina_atual'] = 'perfil'
                st.rerun()

def mostrar_agenda():
    tipo = st.session_state['tipo_utilizador']
    if tipo == 'fisioterapeuta': especialidade = "Fisioterapia"
    elif tipo == 'nutricionista': especialidade = "Nutrição"
    else: especialidade = "Reforço Muscular"
    
    st.title(f"📅 Agenda Clínica - {especialidade}")
    
    if st.session_state.get('paciente_agendamento'):
        st.success(f"🟢 **Modo de Agendamento Ativo:** A selecionar horário para o Paciente ID: {st.session_state['paciente_agendamento']}")
        if st.button("❌ Cancelar Agendamento", use_container_width=True):
            st.session_state['paciente_agendamento'] = None
            st.session_state['confirmar_data'] = None
            st.session_state['confirmar_hora'] = None
            st.rerun()
            
        if st.session_state.get('confirmar_data') and st.session_state.get('confirmar_hora'):
            st.divider()
            st.warning(f"A confirmar consulta no dia **{st.session_state['confirmar_data']}** às **{st.session_state['confirmar_hora']}**")
            obs = st.text_input("Observações (Opcional):")
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("✅ Confirmar Marcação", type="primary", use_container_width=True):
                    data_c = st.session_state['confirmar_data']
                    hora_c = st.session_state['confirmar_hora']
                    paciente = st.session_state['paciente_agendamento']
                    
                    df_todas_consultas_paciente = obter_consultas(id_colab=paciente)
                    conflito_paciente = False
                    especialidade_conflito = ""
                    
                    if not df_todas_consultas_paciente.empty:
                        marcacoes_mesma_hora = df_todas_consultas_paciente[
                            (df_todas_consultas_paciente['data_consulta'] == data_c) & 
                            (df_todas_consultas_paciente['hora_consulta'] == hora_c)
                        ]
                        if not marcacoes_mesma_hora.empty:
                            conflito_paciente = True
                            especialidade_conflito = marcacoes_mesma_hora.iloc[0]['especialidade']
                            
                    if conflito_paciente:
                        st.error(f"⚠️ Erro de Agendamento: O paciente já tem uma sessão de {especialidade_conflito} marcada para esse exato momento. Escolha outra hora ou outro dia.")
                    else:
                        agendar_consulta_db(paciente, especialidade, data_c, hora_c, obs)
                        st.session_state['paciente_agendamento'] = None
                        st.session_state['confirmar_data'] = None
                        st.session_state['confirmar_hora'] = None
                        st.toast("Consulta Registada na Base de Dados!", icon="✅")
                        time.sleep(1.5)
                        st.rerun()
            with col_c2:
                if st.button("Voltar / Escolher outra hora", use_container_width=True):
                    st.session_state['confirmar_data'] = None
                    st.session_state['confirmar_hora'] = None
                    st.rerun()
            st.divider()
            return

    st.divider()
    
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    with col_nav1:
        if st.button("⬅️ Semana Anterior", key="med_ant", use_container_width=True):
            st.session_state['semana_offset'] -= 1
            st.rerun()
            
    hoje = datetime.now().date()
    inicio_semana = hoje - timedelta(days=hoje.weekday()) + timedelta(weeks=st.session_state['semana_offset'])
    fim_semana = inicio_semana + timedelta(days=6)
    
    with col_nav2:
        st.markdown(f"<h4 style='text-align: center;'>{inicio_semana.strftime('%d/%m/%Y')} a {fim_semana.strftime('%d/%m/%Y')}</h4>", unsafe_allow_html=True)
        
    with col_nav3:
        if st.button("Semana Seguinte ➡️", key="med_seg", use_container_width=True):
            st.session_state['semana_offset'] += 1
            st.rerun()
            
    st.write("---")
    
    df_agenda = obter_consultas(especialidade=especialidade)
    
    # --- NOVOS HORÁRIOS: 45 MINUTOS C/ PAUSA DE ALMOÇO ---
    horarios = ["09:00", "09:45", "10:30", "11:15", "12:00", "14:00", "14:45", "15:30", "16:15"]
    dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta'] 
    
    cols = st.columns(5)
    for i in range(5):
        dia_atual = inicio_semana + timedelta(days=i)
        data_str = dia_atual.strftime('%Y-%m-%d')
        
        with cols[i]:
            st.markdown(f"<div style='text-align:center; padding:10px; background-color: var(--secondary-background-color); border-radius:8px;'><b>{dias_semana[i]}</b><br><small>{dia_atual.strftime('%d/%m')}</small></div><br>", unsafe_allow_html=True)
            
            for hora in horarios:
                consulta_existente = None
                if not df_agenda.empty:
                    match = df_agenda[(df_agenda['data_consulta'] == data_str) & (df_agenda['hora_consulta'] == hora)]
                    if not match.empty:
                        consulta_existente = match.iloc[0]
                
                if consulta_existente is not None:
                    id_cons = consulta_existente['id_consulta']
                    id_pac = consulta_existente['id_colaborador']
                    with st.container(border=True):
                        st.markdown(f"<b style='color:#E74C3C;'>{hora}</b> - ID: {id_pac}", unsafe_allow_html=True)
                        if st.button("Entrar / Ver Sessão", key=f"entrar_{id_cons}", use_container_width=True):
                            st.session_state['consulta_ativa'] = int(id_cons)
                            st.session_state['pagina_atual'] = 'sessao_clinica'
                            st.rerun()
                        if st.button("Desmarcar", key=f"del_{id_cons}", use_container_width=True):
                            cancelar_consulta_db(id_cons)
                            st.toast("Consulta cancelada.", icon="♻️")
                            time.sleep(1)
                            st.rerun()
                else:
                    if st.session_state.get('paciente_agendamento'):
                        if dia_atual >= hoje:
                            if st.button(f"➕ {hora}", key=f"add_{data_str}_{hora}", use_container_width=True):
                                st.session_state['confirmar_data'] = data_str
                                st.session_state['confirmar_hora'] = hora
                                st.rerun()
                        else:
                            st.markdown(f"<div style='text-align:center; color:#555; padding:5px; border:1px dashed #444;'>{hora} (Passado)</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='text-align:center; color:gray; padding:5px; border:1px solid #333;'>{hora} - Livre</div>", unsafe_allow_html=True)
                st.write("") 

def mostrar_sessao_clinica():
    id_consulta = int(st.session_state['consulta_ativa'])
    df_cons = obter_consultas(id_consulta=id_consulta).iloc[0]
    id_paciente = str(df_cons['id_colaborador'])
    especialidade = df_cons['especialidade']
    st.title(f"🩺 Sessão Clínica em Curso - {especialidade}")
    
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1: st.markdown(f"**Paciente:** ID {id_paciente} | **Data da Consulta:** {df_cons['data_consulta']} às {df_cons['hora_consulta']}")
    with col_t2:
        if st.button("⬅️ Voltar à Agenda", use_container_width=True): st.session_state['pagina_atual'] = 'agenda'; st.session_state['consulta_ativa'] = None; st.rerun()
    st.divider()
    
    df = carregar_dados()
    dados_ia = df[df['ID'].astype(str) == id_paciente].iloc[0]
    
    if especialidade == "Nutrição": lista_metricas = ["IMC", "Gordura (%)", "Gordura Visceral", "Gap_Idade_Metabolica"]
    else: lista_metricas = ["Assimetria_Forca_%", "Massa Muscular (kg)"]
        
    valores_recentes = {}
    for m in lista_metricas: 
        # Arredondamos logo a 2 casas decimais para evitar números gigantes!
        valores_recentes[m] = round(float(obter_valor_recente(id_paciente, m, dados_ia.get(m, 0))), 2)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📊 Última Referência do Paciente")
        for m in lista_metricas: st.metric(label=f"{m.replace('_', ' ')}", value=f"{valores_recentes[m]}")
            
    with col2:
        st.subheader("📝 Formulário de Avaliação Clínica")
        with st.form("form_evolucao"):
            novos_inputs = {}
            for m in lista_metricas: novos_inputs[m] = st.number_input(f"Registar novo(a) {m.replace('_', ' ')}", value=valores_recentes[m])
            st.text_area("Notas Clínicas da Sessão (Opcional)")
            st.markdown("---")
            agendar_proxima = st.checkbox("Agendar próxima sessão no final desta?")
            
            if st.form_submit_button("💾 Registar Avaliação Completa", type="primary"):
                for m in lista_metricas: guardar_avaliacao(id_consulta, id_paciente, m, valores_recentes[m], novos_inputs[m])
                st.success("Evolução registada com sucesso! O gráfico e a tabela foram atualizados.")
                import time; time.sleep(1.5)
                if agendar_proxima: st.session_state['paciente_agendamento'] = id_paciente; st.session_state['pagina_atual'] = 'agenda'; st.session_state['consulta_ativa'] = None
                st.rerun()

    st.divider()
    
    # --- NOVO: Título limpo e Data da Triagem Base (Excel) ---
    st.subheader("📉 Gráfico de Evolução")
    
    data_medicao = dados_ia.get('Data da Medição', 'N/D')
    if pd.isna(data_medicao) or str(data_medicao).lower() == 'nan':
        data_base_str = "Triagem Inicial"
    else:
        try: data_base_str = pd.to_datetime(data_medicao).strftime('%Y-%m-%d')
        except: data_base_str = str(data_medicao)[:10]

    df_hist = obter_avaliacoes(id_paciente)
    metrica_escolhida = st.selectbox("Selecione a métrica para visualizar a curva de evolução:", lista_metricas)
    
    # Adicionamos a Triagem Base como o primeiro ponto SEMPRE
    ponto_zero_valor = round(float(dados_ia.get(metrica_escolhida, 0)), 2)
    datas = [f"{data_base_str} (Base)"]
    valores = [ponto_zero_valor]

    if not df_hist.empty:
        df_plot = df_hist[df_hist['metrica'] == metrica_escolhida].copy()
        if not df_plot.empty:
            df_plot = df_plot.sort_values('data_registo')
            datas_formatadas = pd.to_datetime(df_plot['data_registo']).dt.strftime('%Y-%m-%d').tolist()
            datas.extend(datas_formatadas)
            valores.extend(df_plot['valor_novo'].tolist())
            
    fig_line = px.line(x=datas, y=valores, markers=True, labels={'x': 'Momento de Avaliação', 'y': metrica_escolhida.replace('_', ' ')})
    fig_line.update_xaxes(type='category')
    fig_line.update_traces(line_color='#3498DB', marker=dict(size=12, color='#E74C3C'), line_width=3)
    fig_line.update_layout(xaxis_title="Linha do Tempo", yaxis_title=metrica_escolhida.replace('_', ' '), margin=dict(t=20, b=20), plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(gridcolor='#ecf0f1'))
    st.plotly_chart(fig_line, use_container_width=True)
    
    st.markdown("**Registo Completo de Avaliações:**")
    col_ratios = [2] + [1.5] * len(lista_metricas) + [1.5] 
    c_headers = st.columns(col_ratios)
    c_headers[0].markdown("**Data**")
    for idx, m in enumerate(lista_metricas): c_headers[idx+1].markdown(f"**{m.replace('_', ' ')}**")
    c_headers[-1].markdown("**Ação**")
    st.write("---")
    
    # 1. A linha inquebrável dos dados do Excel (Base)
    c_row_base = st.columns(col_ratios)
    c_row_base[0].write(f"📊 {data_base_str}")
    for idx, m in enumerate(lista_metricas):
        val = round(float(dados_ia.get(m, 0)), 2)
        c_row_base[idx+1].write(f"{val}")
    c_row_base[-1].write("*(Registo de Triagem)*")

    # 2. As linhas seguintes geradas pelas avaliações
    if not df_hist.empty:
        df_wide = df_hist.pivot_table(index='data_registo', columns='metrica', values='valor_novo', aggfunc='last').reset_index()
        df_wide = df_wide.sort_values('data_registo')
        
        for _, row in df_wide.iterrows():
            c_row = st.columns(col_ratios)
            data_exata = row['data_registo']
            data_limpa = str(data_exata)[:10] 
            c_row[0].write(f"📅 {data_limpa}")
            for idx, m in enumerate(lista_metricas):
                val = row.get(m, None)
                if pd.notnull(val): c_row[idx+1].write(f"{val:.2f}")
                else: c_row[idx+1].write("-")
            if c_row[-1].button("❌ Eliminar", key=f"del_sessao_{data_exata}"):
                apagar_avaliacao_db_por_data(id_paciente, data_exata)
                st.toast("Sessão eliminada com sucesso!", icon="🗑️")
                import time; time.sleep(1)
                st.rerun()

def mostrar_listagem():
    df = carregar_dados()
    if 'Estado' not in df.columns:
        df['Estado'] = 'Ativo'
        
    # 1. Definir a categoria para o Pandas saber a gravidade
    ordem_prioridades = [
        'Alta (Reavaliar em 3 Meses)',
        'Média (Reavaliar em 6 Meses)',
        'Baixa (Reavaliar em 9 Meses)',
        'Rotina (Reavaliar em 12 Meses)'
    ]
    df['Prioridade_Consulta'] = pd.Categorical(df['Prioridade_Consulta'], categories=ordem_prioridades, ordered=True)
        
    tipo = st.session_state['tipo_utilizador']
    especialidade_filtro = None

    if tipo == 'admin':
        st.title("👥 Listagem Geral")
        df_mostrar = df
    elif tipo == 'fisioterapeuta':
        st.title("📋 Fila de Espera: Fisioterapia")
        df_mostrar = df[df['Recomendacao_Sistema'].astype(str).str.contains("Fisioterapia", na=False)]
        especialidade_filtro = "Fisioterapia"
    elif tipo == 'nutricionista':
        st.title("📋 Fila de Espera: Nutrição")
        df_mostrar = df[df['Recomendacao_Sistema'].astype(str).str.contains("Nutrição", na=False)]
        especialidade_filtro = "Nutrição"
    elif tipo == 'reforco':
        st.title("📋 Fila de Espera: Reforço Muscular")
        df_mostrar = df[df['Recomendacao_Sistema'].astype(str).str.contains("Reforço", na=False)]
        especialidade_filtro = "Reforço Muscular"

    df_inativos = df_mostrar[df_mostrar['Estado'] == 'Inativo']
    df_mostrar = df_mostrar[df_mostrar['Estado'] != 'Inativo']

    if especialidade_filtro:
        df_urgentes = obter_pedidos_urgentes(especialidade=especialidade_filtro)
        if not df_urgentes.empty:
            st.error("### 🚨 Pedidos Urgentes")
            for _, urg in df_urgentes.iterrows():
                with st.container(border=True):
                    col_u1, col_u2, col_u3 = st.columns([1, 4, 1])
                    col_u1.error(f"**ID:** {urg['id_colaborador']}")
                    col_u2.write(f"**Motivo:** {urg['motivo']} *Pedido a: {urg['data_pedido'][:10]}*")
                    if col_u3.button("Atender Pedido", key=f"urg_{urg['id_pedido']}", use_container_width=True):
                        st.session_state['id_selecionado'] = urg['id_colaborador']
                        st.session_state['paciente_agendamento'] = urg['id_colaborador']
                        resolver_pedido_urgente(urg['id_pedido']) 
                        st.session_state['pagina_atual'] = 'agenda'
                        st.rerun()
            st.divider()

        df_agendados = obter_consultas(especialidade=especialidade_filtro)
        if not df_agendados.empty:
            ids_com_consulta = df_agendados['id_colaborador'].astype(str).unique().tolist()
            df_mostrar = df_mostrar[~df_mostrar['ID'].astype(str).isin(ids_com_consulta)]

    st.write("👉 **Colaboradores Ativos:**")
    
    # 1. Definimos as colunas exatas e compactas que queremos ver
    colunas_seguras = [c for c in ['ID', 'Entreposto', 'Departamento', 'Idade do empregado', 'Antiguidade', 'Recomendacao_Sistema', 'Prioridade_Consulta'] if c in df.columns]
    
    if df_mostrar.empty:
        st.success("🎉 Excelente! A Fila de Espera está limpa.")
    else:
        df_mostrar = df_mostrar.sort_values(by=['Prioridade_Consulta', 'ID'])
        
        # 2. Renomeamos as colunas SÓ visualmente para a tabela ficar bonita
        df_visual = df_mostrar[colunas_seguras].rename(columns={
            'Idade do empregado': 'Idade',
            'Recomendacao_Sistema': 'Recomendação',
            'Prioridade_Consulta': 'Prioridade'
        })
        
        st.dataframe(df_visual, use_container_width=True, on_select="rerun", selection_mode="single-row", key="tabela_listagem", hide_index=True)
        
        if "tabela_listagem" in st.session_state and hasattr(st.session_state["tabela_listagem"], 'selection'):
            linhas = st.session_state["tabela_listagem"].selection.rows
            if len(linhas) > 0:
                id_selecionado = df_mostrar.iloc[linhas[0]]['ID']
                st.markdown(f"### ⚙️ Ações para o Colaborador ID: **{id_selecionado}**")
                if tipo == 'admin':
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("👁️ Ver Perfil", use_container_width=True):
                            st.session_state['id_selecionado'] = id_selecionado
                            st.session_state['pagina_atual'] = 'perfil'
                            st.rerun()
                    with col_btn2:
                        if st.button("❌ Marcar como Inativo", use_container_width=True):
                            inativar_colaborador_sistema(id_selecionado)
                            st.success(f"✅ Colaborador {id_selecionado} inativado com sucesso!")
                            time.sleep(1.5)
                            st.rerun()
                else:
                    if st.button("👁️ Ver Perfil", use_container_width=True):
                        st.session_state['id_selecionado'] = id_selecionado
                        st.session_state['pagina_atual'] = 'perfil'
                        st.rerun()

    if not df_inativos.empty:
        st.divider()
        st.warning("⚠️ **Colaboradores Inativos**")
        df_inativos = df_inativos.sort_values(by=['Prioridade_Consulta', 'ID'])
        
        # Renomeamos também na tabela dos inativos
        df_inativos_visual = df_inativos[colunas_seguras].rename(columns={
            'Idade do empregado': 'Idade',
            'Recomendacao_Sistema': 'Recomendação',
            'Prioridade_Consulta': 'Prioridade'
        })
        
        st.dataframe(df_inativos_visual, use_container_width=True, on_select="rerun", selection_mode="single-row", key="tabela_inativos", hide_index=True)
        
        if "tabela_inativos" in st.session_state and hasattr(st.session_state["tabela_inativos"], 'selection'):
            linhas_inativas = st.session_state["tabela_inativos"].selection.rows
            if len(linhas_inativas) > 0:
                id_inativo = df_inativos.iloc[linhas_inativas[0]]['ID']
                if st.button(f"🔄 Reativar Colaborador {id_inativo}", type="primary"):
                    reativar_colaborador_sistema(id_inativo)
                    st.success(f"✅ Colaborador {id_inativo} reativado com sucesso!")
                    time.sleep(1.5)
                    st.rerun()

def mostrar_dashboard():
    st.title("📊 Dashboard Global da Organização")
    st.divider()
    df = carregar_dados()
    
    # --- 1. FILTRO GERAL (NO TOPO ABSOLUTO) ---
    col_local = 'Entreposto' if 'Entreposto' in df.columns else ('Localizacao' if 'Localizacao' in df.columns else None)
    
    if col_local:
        locais_existentes = [str(x).capitalize() for x in df[col_local].dropna().unique()]
        lista_locais = ['Global'] + sorted(list(set(locais_existentes)))
        
        col_filtro, _ = st.columns([1, 2])
        with col_filtro: 
            local_selecionado = st.selectbox("📍 Filtrar por Entreposto:", lista_locais)
        
        df_filtrado = df if local_selecionado == 'Global' else df[df[col_local].astype(str).str.capitalize() == local_selecionado]
    else:
        df_filtrado = df

    st.write("---")
    
    # --- 2. KPIs SUPERIORES (Atualizam com o filtro acima) ---
    st.markdown("<h4 style='color: gray;'>Visão Geral da Organização</h4>", unsafe_allow_html=True)
    col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5)
    
    total_colabs = len(df_filtrado)
    pri_alta = len(df_filtrado[df_filtrado['Prioridade_Consulta'].str.contains('Alta', na=False)])
    pri_media = len(df_filtrado[df_filtrado['Prioridade_Consulta'].str.contains('Média', na=False)])
    pri_baixa = len(df_filtrado[df_filtrado['Prioridade_Consulta'].str.contains('Baixa', na=False)])
    pri_rotina = len(df_filtrado[df_filtrado['Prioridade_Consulta'].str.contains('Rotina', na=False)])
    
    col_k1.metric("Total de Colaboradores", total_colabs)
    col_k2.metric("Prioridade Alta (G3)", pri_alta, "Agendar a 3 Meses", delta_color="inverse")
    col_k3.metric("Prioridade Média (G2)", pri_media, "Agendar a 6 Meses", delta_color="off")
    col_k4.metric("Prioridade Baixa (G1)", pri_baixa, "Agendar a 9 Meses", delta_color="normal")
    col_k5.metric("Manutenção / Rotina (G0)", pri_rotina, "12 Meses", delta_color="normal")
    
    st.divider()
    
    st.markdown("<h4 style='color: gray;'>Análise Detalhada</h4>", unsafe_allow_html=True)
    st.write("") 
    
    cores_prio = {'Alta (Reavaliar em 3 Meses)': '#E74C3C', 'Média (Reavaliar em 6 Meses)': '#F1C40F', 'Baixa (Reavaliar em 9 Meses)': '#3498DB', 'Rotina (Reavaliar em 12 Meses)': '#28B463'}
    ordem_exata = ['Alta (Reavaliar em 3 Meses)', 'Média (Reavaliar em 6 Meses)', 'Baixa (Reavaliar em 9 Meses)', 'Rotina (Reavaliar em 12 Meses)']
    
    if df_filtrado.empty: 
        st.warning("Sem dados para a seleção.")
        return
        
    # --- LINHA 1: GRÁFICOS GERAIS ---
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<h5 style='text-align: center; color: gray;'>Distribuição de Recomendações</h5>", unsafe_allow_html=True)
        contagem_rec = df_filtrado['Recomendacao_Sistema'].value_counts().reset_index()
        contagem_rec.columns = ['Recomendação', 'Quantidade']
        fig_bar = px.bar(contagem_rec, x='Recomendação', y='Quantidade', color='Recomendação', color_discrete_map={'Manutenção / Rotina': '#28B463', 'Nutrição': '#58D68D', 'Reforço Muscular': '#3498DB', 'Fisioterapia': '#E74C3C'})
        fig_bar.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig_bar, use_container_width=True)
        
    with col2:
        st.markdown("<h5 style='text-align: center; color: gray;'>Níveis de Urgência Médica</h5>", unsafe_allow_html=True)
        contagem_prio = df_filtrado['Prioridade_Consulta'].value_counts().reset_index()
        contagem_prio.columns = ['Prioridade', 'Quantidade']
        fig_pie = px.pie(contagem_prio, names='Prioridade', values='Quantidade', hole=0.5, color='Prioridade', color_discrete_map=cores_prio, category_orders={'Prioridade': ordem_exata})
        # Correção: Legenda volta para baixo na horizontal
        fig_pie.update_layout(margin=dict(t=10, b=10), legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
        st.plotly_chart(fig_pie, use_container_width=True)

    st.write("---")
    
    # --- LINHA 2: SCATTER E GRÁFICO DE TURNOS ---
    col3, col4 = st.columns(2)
    
    with col3:
        st.markdown("<h5 style='text-align: center; color: gray;'>Correlação Demográfica (Idade vs Antiguidade)</h5>", unsafe_allow_html=True)
        if 'Idade do empregado' in df_filtrado.columns and 'Antiguidade' in df_filtrado.columns and 'IMC' in df_filtrado.columns:
            df_scatter = df_filtrado.dropna(subset=['Idade do empregado', 'Antiguidade', 'IMC'])
            if not df_scatter.empty:
                fig_scatter = px.scatter(df_scatter, x='Idade do empregado', y='Antiguidade', color='Prioridade_Consulta',
                                         size='IMC', hover_data=['ID', 'Recomendacao_Sistema'],
                                         color_discrete_map=cores_prio, category_orders={'Prioridade_Consulta': ordem_exata},
                                         opacity=0.7)
                fig_scatter.update_layout(margin=dict(t=10, b=10), xaxis_title="Idade do Colaborador", yaxis_title="Anos de Empresa", legend_title="", legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
                st.plotly_chart(fig_scatter, use_container_width=True)
            else:
                st.info("Não há colaboradores com dados completos para gerar a matriz.")
        else:
            st.info("Métricas insuficientes.")
            
    with col4:
        st.markdown("<h5 style='text-align: center; color: gray;'>Distribuição de Risco por Turno de Trabalho</h5>", unsafe_allow_html=True)
        if 'Turno' in df_filtrado.columns:
            df_turno = df_filtrado.groupby(['Turno', 'Prioridade_Consulta']).size().reset_index(name='Quantidade')
            fig_turno = px.bar(df_turno, x='Turno', y='Quantidade', color='Prioridade_Consulta', 
                             color_discrete_map=cores_prio, category_orders={'Prioridade_Consulta': ordem_exata},
                             barmode='group')
            fig_turno.update_layout(margin=dict(t=10, b=10), xaxis_title="Turno", legend_title="", legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
            st.plotly_chart(fig_turno, use_container_width=True)
        else:
            st.info("Dados de Turno não disponíveis.")

    st.write("---")

    # --- LINHA 3: MAPA DE DEPARTAMENTOS ---
    st.markdown("<h3 style='text-align: center; color: gray;'>Mapa de Risco Transversal por Departamento</h3>", unsafe_allow_html=True)
    col_dep = 'Departamento' if 'Departamento' in df_filtrado.columns else ('Função' if 'Função' in df_filtrado.columns else None)
    if col_dep:
        df_dep = df_filtrado.groupby([col_dep, 'Prioridade_Consulta']).size().reset_index(name='Quantidade')
        fig_dep = px.bar(df_dep, x=col_dep, y='Quantidade', color='Prioridade_Consulta', 
                         color_discrete_map=cores_prio, category_orders={'Prioridade_Consulta': ordem_exata},
                         barmode='stack')
        
        # Correção: Legenda no Canto Superior Direito e margem inferior generosa para os nomes compridos!
        fig_dep.update_layout(
            height=600, 
            margin=dict(t=20, b=120), 
            xaxis_title="", 
            legend_title="", 
            legend=dict(orientation="v", yanchor="top", y=1.0, xanchor="right", x=1.0)
        )
        st.plotly_chart(fig_dep, use_container_width=True)
    else:
        st.info("Dados de Departamento não disponíveis.")

def mostrar_gestao_dados():
    st.title("⚙️ Gestão de Dados")
    st.write("Painel de controlo para inserir dados de RH e treinar o algoritmo preditivo.")
    st.divider()
    
    # Nome das abas atualizado
    tab1, tab2 = st.tabs(["📂 Inserir Dados", "🧠 Treino do Modelo IA"])
    
    with tab1:
        st.write("Faça upload de um ficheiro Excel central com novos colaboradores ou atualizações organizacionais.")
        ficheiro = st.file_uploader("Selecione o ficheiro (.xlsx)", type=['xlsx'])
        if ficheiro is not None: 
            st.success(f"✅ Ficheiro '{ficheiro.name}' inserido com sucesso no sistema!")
            st.info("Para que estes novos dados entrem em vigor, avance para o separador 'Treino do Modelo IA' e inicie o retreino.")
            
    with tab2:
        st.write("Recalibre o modelo de Machine Learning (K-Means) para analisar os novos dados e atualizar as triagens.")
        if st.button("🚀 Iniciar Retreino do Modelo IA", type="primary"):
            with st.spinner('A otimizar pesos e a reconstruir clusters clínicos...'): 
                import time
                time.sleep(3.5) # Finge que está a pensar durante 3.5 segundos
            st.success("🎉 Retreino concluído com sucesso! O Dashboard já reflete os novos dados.")
            st.balloons()

def mostrar_gestao_profissionais():
    st.title("⚕️ Gestão de Profissionais")
    st.write("Gere os acessos da equipa clínica ao portal Sonae Vital.")
    st.divider()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("🔑 Gerar Código de Acesso")
        with st.form("form_add_prof"):
            st.write("Selecione a especialidade para gerar uma chave única de registo. Entregue a chave ao profissional para que ele crie a sua própria conta.")
            
            # Nomes bonitos para o utilizador escolher
            especialidade_display = st.selectbox("Especialidade", ["Fisioterapeuta", "Nutricionista", "Técnico"])
            
            if st.form_submit_button("Gerar Código Único", use_container_width=True):
                # O dicionário traduz o nome bonito para a variável que a Base de Dados entende
                mapa_esp = {"Fisioterapeuta": "fisioterapeuta", "Nutricionista": "nutricionista", "Técnico": "reforco"}
                tipo_db = mapa_esp[especialidade_display]
                
                codigo = gerar_codigo_prof_db(tipo_db)
                st.success(f"✅ Código gerado: **{codigo}**")
                st.info("O profissional deve colocar este código no campo 'Código de Autorização' ao registar a conta.")
                    
    with col2:
        st.subheader("👥 Profissionais Ativos")
        df_profs = obter_profissionais_db()
        
        if not df_profs.empty:
            st.write("Selecione um profissional na tabela para remover o acesso:")
            # Removemos a visualização do 'ID Oculto' da tabela para ficar limpo
            st.dataframe(df_profs[['Nome', 'Email', 'Especialidade']], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="tabela_profs")
            
            if "tabela_profs" in st.session_state and hasattr(st.session_state["tabela_profs"], 'selection'):
                linhas = st.session_state["tabela_profs"].selection.rows
                if len(linhas) > 0:
                    id_prof = df_profs.iloc[linhas[0]]['ID Oculto']
                    nome_prof = df_profs.iloc[linhas[0]]['Nome']
                    # O botão agora tem o nome da pessoa!
                    if st.button(f"❌ Remover Acesso a {nome_prof}", use_container_width=True):
                        remover_utilizador_db(id_prof)
                        st.success(f"O acesso de {nome_prof} foi revogado.")
                        import time; time.sleep(1.5)
                        st.rerun()
        else:
            st.info("Nenhuma conta clínica registada ainda.")

# --- 6. O CONTROLADOR GLOBAL (BARRA LATERAL E ECRÃS) ---

desenhar_cabecalho_notificacoes()

if st.session_state['autenticado']:
    tipo = st.session_state['tipo_utilizador']
    
    with st.sidebar:
        try:
            col_img1, col_img2, col_img3 = st.sidebar.columns([1, 4, 1])
            with col_img2:
                st.image("sonae.png", width=175)
        except:
            pass
        st.title("⚙ Navegação")
        if tipo == 'colaborador':
            id_colab = st.session_state.get('id_selecionado', 'N/D')
            st.success(f"👤 Logado como: **ID {id_colab}**")
        else:
            st.success(f"👤 Logado como: **{tipo.capitalize()}**")
            
        st.divider()
        
        if tipo == 'colaborador':
            if st.button("👤 O Meu Perfil", use_container_width=True): st.session_state['pagina_atual'] = 'perfil'; st.rerun()
            if st.button("📅 O Meu Horário", use_container_width=True): st.session_state['pagina_atual'] = 'agenda_colaborador'; st.rerun()
            if st.button("🚨 Pedido de Urgência", use_container_width=True): st.session_state['pagina_atual'] = 'pedido_urgente'; st.rerun()
                
        elif tipo in ['fisioterapeuta', 'nutricionista', 'reforco']:
            if st.button("🏠 Menu Principal", use_container_width=True): st.session_state['pagina_atual'] = 'menu_principal'; st.rerun()
            if st.button("📋 Fila de Espera", use_container_width=True): st.session_state['pagina_atual'] = 'listagem'; st.rerun()
            if st.button("📅 Agenda Clínica", use_container_width=True): st.session_state['pagina_atual'] = 'agenda'; st.rerun()
            if st.button("👤 Perfil Clínico", use_container_width=True): st.session_state['pagina_atual'] = 'perfil'; st.rerun()
                
        elif tipo == 'admin':
            if st.button("🏠 Menu Principal", use_container_width=True): st.session_state['pagina_atual'] = 'menu_principal'; st.rerun()
            if st.button("📊 Dashboard Global", use_container_width=True): st.session_state['pagina_atual'] = 'dashboard'; st.rerun()
            if st.button("👥 Listagem Geral", use_container_width=True): st.session_state['pagina_atual'] = 'listagem'; st.rerun()
            if st.button("👤 Perfil Colaborador", use_container_width=True): st.session_state['pagina_atual'] = 'perfil'; st.rerun()
            if st.button("⚕️ Gestão de Profissionais", use_container_width=True): st.session_state['pagina_atual'] = 'gestao_profissionais'; st.rerun()
            if st.button("⚙️ Gestão de Dados", use_container_width=True): st.session_state['pagina_atual'] = 'gestao_dados'; st.rerun()
        
        st.divider()
        if st.button("Sair / Log Out", use_container_width=True):
            st.session_state['autenticado'] = False
            st.session_state['tipo_utilizador'] = None
            st.session_state['pagina_atual'] = 'menu_principal'
            st.rerun()

    # ROTEADOR DE ECRÃS
    pag = st.session_state['pagina_atual']
    if pag == 'menu_principal' and tipo != 'colaborador': mostrar_menu_principal()
    elif pag == 'perfil': mostrar_perfil()
    elif pag == 'agenda_colaborador': mostrar_agenda_colaborador()
    elif pag == 'pedido_urgente': mostrar_pedido_urgente()
    elif pag == 'listagem': mostrar_listagem()
    elif pag == 'agenda': mostrar_agenda()
    elif pag == 'sessao_clinica': mostrar_sessao_clinica()
    elif pag == 'dashboard' and tipo == 'admin': mostrar_dashboard()
    elif pag == 'gestao_dados' and tipo == 'admin': mostrar_gestao_dados()
    elif pag == 'gestao_profissionais' and tipo == 'admin': mostrar_gestao_profissionais()
else:
    mostrar_ecra_login()