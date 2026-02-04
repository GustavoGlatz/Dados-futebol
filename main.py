import os
import json
import logging
import requests
import boto3
from datetime import datetime
from dotenv import load_dotenv


logger = logging.getLogger()
logger.setLevel(logging.INFO)

load_dotenv()

class FootballDataOrgETL:
    def __init__(self):
        # Configurações da API de Futebol
        self.base_url = "https://api.football-data.org/v4"
        self.api_key = os.getenv("API_FOOTBALL_DATA_KEY")
        
        if not self.api_key:
            raise ValueError("ERRO: Chave da API não encontrada.")

        self.headers = { "X-Auth-Token": self.api_key }
        
        self.competitions_strategy = {
            "BSA": "MATCHDAY",   
            "2152": "MATCHDAY",  
            "CL": "DATE"
        }

        # Configurações da AWS S3
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        if not self.bucket_name:
            raise ValueError("ERRO: Variável AWS_S3_BUCKET_NAME não definida.")

        self.s3_client = boto3.client('s3')

    def _get_current_matchday(self, competition_id):
        """Busca o número da rodada atual para uma competição"""
        endpoint = f"{self.base_url}/competitions/{competition_id}"
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("currentSeason", {}).get("currentMatchday")
            else:
                logging.warning(f"Não foi possível obter matchday para {competition_id}: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"Erro ao buscar matchday ({competition_id}): {e}")
            return None

    def get_matches(self):
        """Busca os dados aplicando a estratégia correta por liga"""
        today = datetime.now().strftime("%Y-%m-%d")
        current_year = datetime.now().year
        all_matches_data = []

        for competition_id, strategy in self.competitions_strategy.items():
            matches = []
            
            # Ajuste de ano para Champions League (Season europeia começa ano anterior)
            season = current_year - 1 if competition_id == "CL" else current_year
            
            try:
                if strategy == "MATCHDAY":
                    matchday = self._get_current_matchday(competition_id)
                    
                    if matchday:
                        logging.info(f"Buscando {competition_id} pela rodada {matchday}...")
                        endpoint = f"{self.base_url}/competitions/{competition_id}/matches"
                        params = {"season": season, "matchday": matchday}
                        
                        response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
                        if response.status_code == 200:
                            matches = response.json().get("matches", [])
                    else:
                        logging.warning(f"Pular {competition_id}: Matchday não encontrado.")

                else:
                    logging.info(f"Buscando {competition_id} por data ({today})...")
                    endpoint = f"{self.base_url}/competitions/{competition_id}/matches"
                    params = {"season": season, "dateFrom": today, "dateTo": today}
                    
                    response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
                    if response.status_code == 200:
                        matches = response.json().get("matches", [])

                if matches:
                    all_matches_data.append({
                        "competition_code": competition_id,
                        "extraction_date": today,
                        "season": season,
                        "matches": matches
                    })
                    logging.info(f"[{competition_id}] Dados encontrados: {len(matches)} partidas.")
                else:
                    logging.info(f"[{competition_id}] Nenhuma partida retornada.")

            except Exception as e:
                logging.error(f"Erro processando {competition_id}: {e}")

        return all_matches_data

    def save_to_s3(self, data):
        """
        Salva os dados diretamente no S3 na pasta 'raw/'.
        """
        if not data:
            logging.warning("Nenhum dado para salvar no S3.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"matches_data_{timestamp}.json"
        
        # Aqui definimos a 'pasta' raw/ concatenando no nome
        s3_key = f"raw/{filename}"

        try:
            # Serialização em Memória
            # json.dumps converte o objeto Python (dict) para String JSON
            json_string = json.dumps(data, ensure_ascii=False, indent=4)
            
            # Converter string para bytes (padrão UTF-8)
            json_bytes = json_string.encode('utf-8')

            logging.info(f"Iniciando upload para s3://{self.bucket_name}/{s3_key}")

            # Upload usando put_object
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json_bytes,
                ContentType='application/json'
            )

            logging.info("Upload concluído com sucesso!")

        except boto3.exceptions.Boto3Error as e:
            # Captura erros específicos da AWS
            logging.error(f"Erro AWS S3: {e}")
        except Exception as e:
            logging.error(f"Erro genérico ao salvar no S3: {e}")

def lambda_handler(event, context):
    """
    Função que a AWS chama quando o relógio despertar.
    'event': Dados sobre o gatilho (não usaremos aqui)
    'context': Dados sobre o ambiente de execução
    """
    logger.info("Iniciando execução via Lambda...")
    
    try:
        etl = FootballDataOrgETL()
        data = etl.get_matches()
        etl.save_to_s3(data)
        
        return {
            'statusCode': 200,
            'body': 'ETL Executado com Sucesso!'
        }
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        raise e

if __name__ == "__main__":
    try:
        etl = FootballDataOrgETL()
        data = etl.get_matches()
        etl.save_to_s3(data)
    except Exception as e:
        logging.critical(f"Falha fatal: {e}")