import sys
import boto3
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from datetime import datetime
from pyspark.sql.functions import *
from delta.tables import *
from pyspark.sql.window import Window

# Configuração Inicial do Glue
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'BUCKET_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

job = Job(glueContext)
job.init(args['JOB_NAME'], args)

bucket_name = args['BUCKET_NAME']
base_path = f"s3://{bucket_name}"
bronze_path = f"{base_path}/bronze/matches_history"
path_silver = f"{base_path}/silver/matches_cleaned"
gold_path = f"{base_path}/gold/daily_league_stats"

# LEITURA DO ARQUIVO RAW
data_hoje = datetime.now().strftime("%Y%m%d")
caminho_arquivo_hoje = f"{base_path}/raw/matches_data_{data_hoje}_*.json"

try:
    df_raw = spark.read.option("multiline", "true").json(caminho_arquivo_hoje)
except Exception as e:
    print(f"ERRO: Nenhum arquivo encontrado para a data {data_hoje} no caminho {caminho_arquivo_hoje}")
    sys.exit(0)

# CAMADA BRONZE 
df_bronze = df_raw.withColumn("ingestion_date", to_date(current_timestamp())) \
                  .withColumn("source_file", input_file_name())

df_bronze.cache()
df_bronze.write.format("delta").mode("append").save(bronze_path)

# CAMADA PRATA 
df_exploded = df_bronze.withColumn("match", explode(col("matches")))

df_cleaned = df_exploded.select(
    col("competition_code"),
    col("season"),
    col("match.id").alias("match_id"),
    to_timestamp(col("match.utcDate")).alias("match_date_full"),
    date_format(
        from_utc_timestamp(to_timestamp(col("match.utcDate")), "America/Sao_Paulo"), 
        "HH:mm"
    ).alias("match_time"),
    col("match.status").alias("status"),
    col("match.homeTeam.name").alias("home_team"),
    col("match.awayTeam.name").alias("away_team"),
    col("match.score.fullTime.home").alias("score_home"),
    col("match.score.fullTime.away").alias("score_away"),
    col("match.homeTeam.crest").alias("logo_home"),
    col("match.awayTeam.crest").alias("logo_away"),
    col("ingestion_date")
)

leagues_data = [
("CL", "Champions League"),
("BSA", "Brasileirão Série A"),
("2152", "Copa Libertadores")
]
df_leagues = spark.createDataFrame(leagues_data, ["code", "league_name"])

df_enriched = df_cleaned.join(
    df_leagues,
    df_cleaned.competition_code == df_leagues.code,
    "left"
).drop("code")

w = Window.partitionBy("match_id").orderBy(col("ingestion_ts").desc())
df_silver = df_enriched.withColumn("rn", row_number().over(w)).filter(col("rn") == 1).drop("rn")

df_silver.cache()

if DeltaTable.isDeltaTable(spark, path_silver):
    deltaTable = DeltaTable.forPath(spark, path_silver)
    
    (
        deltaTable.alias("target")
        .merge(
            df_silver.alias("source"),
            "target.match_id = source.match_id"
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )

else:
    df_silver.write.format("delta").mode("overwrite").save(path_silver)


# CAMADA OURO
df_silver.createOrReplaceTempView("silver_matches")

df_gold = spark.sql("""
    SELECT 
        league_name,
        DATE(match_date_full) as match_day,
        COUNT(match_id) as total_matches,
        SUM(score_home + score_away) as total_goals,
        ROUND(AVG(score_home + score_away), 2) as avg_goals_match
    FROM silver_matches
    GROUP BY 
        league_name, 
        DATE(match_date_full)
    ORDER BY 
        match_day DESC, 
        total_goals DESC
    """)

df_gold.write.format("delta").mode("overwrite").save(gold_path)

df_bronze.unpersist()
df_silver.unpersist()

job.commit()