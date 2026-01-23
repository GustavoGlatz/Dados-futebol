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
        # 1. Configurações da API de Futebol
        self.base_url = "https://api.football-data.org/v4"
        self.api_key = os.getenv("API_FOOTBALL_DATA_KEY") or os.getenv("API_FOOTBALL_KEY")
        
        if not self.api_key:
            raise ValueError("ERRO: Chave da API não encontrada.")

        self.headers = { "X-Auth-Token": self.api_key }
        self.competitions = ["BSA", "CL"]

        # 2. Configurações da AWS S3
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        if not self.bucket_name:
            raise ValueError("ERRO: Variável AWS_S3_BUCKET_NAME não definida.")

        # O boto3 busca credenciais automaticamente (Env vars, ~/.aws/credentials ou IAM Role)
        self.s3_client = boto3.client('s3')

    def get_matches(self):
        """Busca os dados (Mantido igual ao passo anterior)"""
        today = datetime.now().strftime("%Y-%m-%d")
        current_year = datetime.now().year
        all_matches_data = []

        for competition_id in self.competitions:
            if competition_id == "CL":
                season = current_year - 1
            else:
                season = current_year

            params = { "season": season, "dateFrom": today, "dateTo": today }
            endpoint = f"{self.base_url}/competitions/{competition_id}/matches"

            try:
                logging.info(f"Buscando {competition_id}...")
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
                        logging.info(f"Dados encontrados: {len(matches)} partidas.")
                else:
                    logging.warning(f"Falha na API ({competition_id}): {response.status_code}")

            except Exception as e:
                logging.error(f"Erro de conexão: {e}")

        return all_matches_data

    def save_to_s3(self, data):
        """
        Salva os dados diretamente no S3 na pasta 'raw/'.
        """
        if not data:
            logging.warning("Nenhum dado para salvar no S3.")
            return

        # 1. Definição do Nome do Arquivo (Key)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"matches_data_{timestamp}.json"
        
        # Aqui definimos a 'pasta' raw/ concatenando no nome
        s3_key = f"raw/{filename}"

        try:
            # 2. Serialização em Memória
            # json.dumps converte o objeto Python (dict) para String JSON
            json_string = json.dumps(data, ensure_ascii=False, indent=4)
            
            # Converter string para bytes (padrão UTF-8)
            json_bytes = json_string.encode('utf-8')

            logging.info(f"Iniciando upload para s3://{self.bucket_name}/{s3_key}")

            # 3. Upload usando put_object
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json_bytes,
                ContentType='application/json'  # Importante para visualização correta no console AWS
            )

            logging.info("Upload concluído com sucesso!")

        except boto3.exceptions.Boto3Error as e:
            # Captura erros específicos da AWS (ex: Bucket não existe, Sem permissão)
            logging.error(f"Erro AWS S3: {e}")
        except Exception as e:
            logging.error(f"Erro genérico ao salvar no S3: {e}")

def lambda_handler(event, context):
    """
    Esta é a função que a AWS chama quando o relógio despertar.
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