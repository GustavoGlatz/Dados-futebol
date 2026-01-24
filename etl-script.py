import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import current_timestamp, input_file_name, col, explode, to_date, sum, count, round, avg, to_timestamp 

# Configuração Inicial do Glue

# Le as "variáveis de ambiente" passadas pelo terraform
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'BUCKET_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

job = Job(glueContext)
job.init(args['JOB_NAME'], args)

bucket_name = args['BUCKET_NAME']
base_path = f"s3://{bucket_name}"


# CAMADA BRONZE (Raw JSON -> Parquet)
# Lê os JSONs da pasta raw
df_raw = spark.read.option("multiline", "true").json(f"{base_path}/raw/*.json")

# Adiciona metadados
df_bronze = df_raw.withColumn("ingestion_date", current_timestamp()) \
                  .withColumn("source_file", input_file_name())

# Salva em Parquet (Sobrescreve para simplificar o exemplo)
df_bronze.write.mode("overwrite").parquet(f"{base_path}/bronze/matches_history")

# CAMADA PRATA (Limpeza e Flattening)
# Lê da Bronze
df_b = spark.read.parquet(f"{base_path}/bronze/matches_history")

# Formata os dados para um formato tabular
df_exploded = df_b.withColumn("match", explode(col("matches")))

# Seleciona e renomeia colunas relevantes (percorre a estrutura aninhada tabulando os dados)
df_silver = df_exploded.select(
    col("competition_code"),
    col("season"),
    col("match.id").alias("match_id"),
    to_timestamp(col("match.utcDate")).alias("match_date"),
    col("match.status").alias("status"),
    col("match.homeTeam.name").alias("home_team"),
    col("match.awayTeam.name").alias("away_team"),
    col("match.score.fullTime.home").alias("score_home"),
    col("match.score.fullTime.away").alias("score_away")
)

df_silver.write.mode("overwrite").parquet(f"{base_path}/silver/matches_cleaned")

# CAMADA OURO (Agregação)
# Criação de View temporária para usar SQL
df_silver.createOrReplaceTempView("silver_matches")

# Agrega os dados para obter estatísticas diárias por competição
df_gold = spark.sql("""
    SELECT 
        competition_code,
        DATE(from_utc_timestamp(match_date, 'America/Sao_Paulo')) as match_day,
        
        COUNT(match_id) as total_matches,
        
        SUM(score_home + score_away) as total_goals,
        
        ROUND(AVG(score_home + score_away), 2) as avg_goals_match

    FROM silver_matches
    
    GROUP BY 
        competition_code, 
        DATE(from_utc_timestamp(match_date, 'America/Sao_Paulo'))
        
    ORDER BY 
        match_day DESC, 
        total_goals DESC
    """)

df_gold.write.mode("overwrite").parquet(f"{base_path}/gold/daily_league_stats")

job.commit()