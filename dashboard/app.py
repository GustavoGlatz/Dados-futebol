import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from deltalake import DeltaTable

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
AWS_REGION = st.secrets["AWS_REGION"]

storage_options = {"key": AWS_KEY, "secret": AWS_SECRET, "region": AWS_REGION}

def get_brasil_date_str():
    brasil_now = datetime.utcnow() - timedelta(hours=3)
    return brasil_now.strftime("%Y-%m-%d")

# Cache de 5 minutos
@st.cache_data(ttl=300)
def load_data():

    data_hoje = get_brasil_date_str()

    try:
        # --- CARREGANDO SILVER ---
        path_silver = f"s3://{BUCKET_NAME}/silver/matches_cleaned"
        dt_silver = DeltaTable(path_silver, storage_options=storage_options)
        df_silver = dt_silver.to_pandas()
        
        if not df_silver.empty:
            df_silver['match_timestamp_br'] = pd.to_datetime(df_silver['match_timestamp_br'])
            df_silver = df_silver[df_silver['match_timestamp_br'].dt.strftime('%Y-%m-%d') == data_hoje]

        # --- CARREGANDO GOLD ---
        path_gold = f"s3://{BUCKET_NAME}/gold/daily_league_stats"
        dt_gold = DeltaTable(path_gold, storage_options=storage_options)
        df_gold = dt_gold.to_pandas()
        
        if not df_gold.empty:
            df_gold['match_day'] = pd.to_datetime(df_gold['match_day'])
            df_gold = df_gold[df_gold['match_day'].dt.strftime('%Y-%m-%d') == data_hoje]

        return df_silver, df_gold
    except Exception as e:
        st.error(f"Não há jogos hoje: {e}")
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

    matches_filtered['score_home'] = matches_filtered['score_home'].fillna(0).astype(int)
    matches_filtered['score_away'] = matches_filtered['score_away'].fillna(0).astype(int)    

    for index, row in matches_filtered.iterrows():
        # colunas: Logo1 | Gols1 | X | Gols2 | Logo2
        c1, c2, c3, c4, c5 = st.columns([1, 1, 0.5, 1, 1])
        
        with c1:
            if 'logo_home' in row and row['logo_home']:
                st.image(row['logo_home'], width=50)
            else:
                st.write(row['home_team'])
        
        with c2:
            st.markdown(f"<div class='score-text'>{row['score_home']}</div>", unsafe_allow_html=True)
            
        with c3:
            horario = row.get('match_time', '--:--')
            st.markdown(f"<div style='text-align: center; font-size: 12px; color: #555; margin-bottom: -10px;'>{horario}</div>", unsafe_allow_html=True)
            st.markdown("<div class='vs-text'>X</div>", unsafe_allow_html=True)
            
        with c4:
            st.markdown(f"<div class='score-text'>{row['score_away']}</div>", unsafe_allow_html=True)
            
        with c5:
            if 'logo_away' in row and row['logo_away']:
                st.image(row['logo_away'], width=50)
            else:
                st.write(row['away_team'])
        
        st.divider()
else:
    st.info("Nenhuma partida encontrada para esta liga hoje.")


# ESTATÍSTICAS
st.subheader(f"Estatísticas da {liga_selecionada if liga_selecionada else '...'}")

if not stats_filtered.empty:
    stats_filtered = stats_filtered.fillna(0) 
    
    stat_row = stats_filtered.iloc[0]
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.metric(
            label="Quantidade de gols na rodada",
            value=int(stat_row['total_goals']) 
        ) 
        
    with col_b:
        st.metric(
            label="Média de gols na rodada",
            value=f"{stat_row['avg_goals_match']:.2f}"
        )
else:
    st.warning("Não há estatísticas para hoje")