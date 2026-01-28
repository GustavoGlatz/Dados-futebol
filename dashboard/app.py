import streamlit as st
import pandas as pd
from datetime import datetime

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(
    page_title="Partidas de Hoje",
    page_icon="⚽",
    layout="centered"
)

# ESTILOS CSS PERSONALIZADOS
st.markdown("""
    <style>
    /* Estilo dos placares */
    .score-text {
        font-size: 24px;
        font-weight: bold;
        text-align: center;
    }
    .vs-text {
        font-size: 18px;
        color: #666;
        text-align: center;
        padding-top: 5px;
    }
    </style>
""", unsafe_allow_html=True)

# CONEXÃO E DADOS 
AWS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
AWS_SECRET = st.secrets["AWS_SECRET_ACCESS_KEY"]
BUCKET_NAME = st.secrets["AWS_S3_BUCKET_NAME"] 

storage_options = {"key": AWS_KEY, "secret": AWS_SECRET}

# Cache de 5 minutos
@st.cache_data(ttl=300)
def load_data():
    try:
        # Carregando SILVER (Partidas detalhadas)
        path_silver = f"s3://{BUCKET_NAME}/silver/matches_cleaned" 
        df_silver = pd.read_parquet(path_silver, storage_options=storage_options)
        
        # Carregando GOLD (Estatísticas agregadas)
        path_gold = f"s3://{BUCKET_NAME}/gold/daily_league_stats"
        df_gold = pd.read_parquet(path_gold, storage_options=storage_options)

        return df_silver, df_gold
    except Exception as e:
        st.error(f"Não há jogos hoje")
        return pd.DataFrame(), pd.DataFrame()

df_matches, df_stats = load_data()

# CABEÇALHO
st.title("Partidas de hoje")

# SELETOR DE LIGA 
if not df_matches.empty:
    ligas_disponiveis = df_matches['league_name'].unique()
    liga_selecionada = st.selectbox("Seletor de liga", ligas_disponiveis)
    
    matches_filtered = df_matches[df_matches['league_name'] == liga_selecionada]
    stats_filtered = df_stats[df_stats['league_name'] == liga_selecionada]
else:
    liga_selecionada = None
    matches_filtered = pd.DataFrame()
    stats_filtered = pd.DataFrame()

# PARTIDAS
st.subheader(f"Jogos da {liga_selecionada if liga_selecionada else '...'}")

if not matches_filtered.empty:
    for index, row in matches_filtered.iterrows():
        # Cria 5 colunas: Logo1 | Gols1 | X | Gols2 | Logo2
        c1, c2, c3, c4, c5 = st.columns([1, 1, 0.5, 1, 1])
        
        with c1:
            # Exibe logo ou nome se não tiver logo
            if 'logo_home' in row and row['logo_home']:
                st.image(row['logo_home'], width=50)
            else:
                st.write(row['home_team'])
        
        with c2:
            st.markdown(f"<div class='score-text'>{row.get('score_home') if row.get('score_home') is not None else 0}</div>", unsafe_allow_html=True)
            
        with c3:
            horario = row.get('match_time', '--:--')
            st.markdown(f"<div style='text-align: center; font-size: 12px; color: #555; margin-bottom: -10px;'>{horario}</div>", unsafe_allow_html=True)
            st.markdown("<div class='vs-text'>X</div>", unsafe_allow_html=True)
            
        with c4:
            st.markdown(f"<div class='score-text'>{row.get('score_away') if row.get('score_away') is not None else 0}</div>", unsafe_allow_html=True)
            
        with c5:
            if 'logo_away' in row and row['logo_away']:
                st.image(row['logo_away'], width=50)
            else:
                st.write(row['away_team'])
        
        st.divider() # Linha divisória entre jogos
else:
    st.info("Nenhuma partida encontrada para esta liga hoje.")


# ESTATÍSTICAS
st.subheader(f"Estatísticas da {liga_selecionada if liga_selecionada else '...'}")

if not stats_filtered.empty:
    stat_row = stats_filtered.iloc[0]
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.metric(
            label="Quantidade de gols na rodada",
            value=stat_row.get('total_goals') if stat_row.get('total_goals') is not None else 0
        ) 
        
    with col_b:
        st.metric(
            label="Média de gols na rodada",
            value=f"{stat_row.get('avg_goals_match') if stat_row.get('avg_goals_match') is not None else 0:.2f}"
        )
else:
    st.warning("Não há estatísticas para hoje")