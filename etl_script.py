import sys
import boto3
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from datetime import datetime, timedelta
from pyspark.sql.functions import *
from delta.tables import *
from pyspark.sql.window import Window
from pyspark.sql.types import IntegerType, StructType, StructField, StringType, LongType, ArrayType


args = getResolvedOptions(sys.argv, ['JOB_NAME', 'BUCKET_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

spark.conf.set("spark.hadoop.fs.s3a.directory.marker.retention", "keep") 
spark.conf.set("spark.sql.sources.commitProtocolClass", "org.apache.spark.sql.execution.datasources.SQLHadoopMapReduceCommitProtocol")
spark.conf.set("mapreduce.fileoutputcommitter.marksuccessfuljobs", "false")

spark.conf.set("spark.databricks.delta.schema.autoMerge.enabled", "true")

bucket_name = args['BUCKET_NAME']
base_path = f"s3://{bucket_name}"

bronze_path = f"{base_path}/bronze/matches_history"
path_silver = f"{base_path}/silver/matches_cleaned"
gold_path = f"{base_path}/gold/daily_league_stats"


utc_now = datetime.utcnow()
brasil_now = utc_now - timedelta(hours=3)

data_arquivo_str = brasil_now.strftime("%Y%m%d")
data_filtro_iso = brasil_now.strftime("%Y-%m-%d")


# RAW
caminho_arquivo_hoje = f"{base_path}/raw/matches_data_{data_arquivo_str}_*.json"

referee_schema = StructType([
    StructField("id", LongType(), True),
    StructField("name", StringType(), True),
    StructField("nationality", StringType(), True),
    StructField("type", StringType(), True),
])

match_schema = StructType([
    StructField("id", LongType(), True),
    StructField("utcDate", StringType(), True),
    StructField("status", StringType(), True),
    StructField("homeTeam", StructType([
        StructField("name", StringType(), True),
        StructField("crest", StringType(), True),
    ]), True),
    StructField("awayTeam", StructType([
        StructField("name", StringType(), True),
        StructField("crest", StringType(), True),
    ]), True),
    StructField("score", StructType([
        StructField("fullTime", StructType([
            StructField("home", LongType(), True),
            StructField("away", LongType(), True),
        ]), True),
    ]), True),
    StructField("referees", ArrayType(referee_schema), True),
])

raw_schema = StructType([
    StructField("competition_code", StringType(), True),
    StructField("extraction_date", StringType(), True),
    StructField("season", LongType(), True),
    StructField("matches", ArrayType(match_schema), True),
])

try:
    df_raw = spark.read.schema(raw_schema).option("multiline", "true").json(caminho_arquivo_hoje)
except Exception as e:
    print(f"ERRO: Nenhum arquivo encontrado em {caminho_arquivo_hoje}. Encerrando Job.")
    sys.exit(0)

# BRONZE
df_bronze = df_raw.withColumn("ingestion_ts", current_timestamp()) \
                  .withColumn("source_file", input_file_name())

df_bronze.coalesce(1).write.format("delta").mode("append").save(bronze_path)

# SILVER
df_exploded = df_bronze.withColumn("match", explode(col("matches")))

df_cleaned = df_exploded.select(
    col("competition_code"),
    col("season"),
    col("match.id").cast(IntegerType()).alias("match_id"),
    to_timestamp(col("match.utcDate")).alias("match_timestamp_utc"),
    from_utc_timestamp(to_timestamp(col("match.utcDate")), "America/Sao_Paulo").alias("match_timestamp_br"),
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
    col("ingestion_ts")
)
df_filtered = df_cleaned.filter(
    to_date(col("match_timestamp_br")) == to_date(lit(data_filtro_iso))
)

leagues_data = [
    ("CL", "Champions League"),
    ("BSA", "Brasileirão Série A"),
    ("2152", "Copa Libertadores")
]
df_leagues = spark.createDataFrame(leagues_data, ["code", "league_name"])

df_enriched = df_filtered.join(
    broadcast(df_leagues),
    df_filtered.competition_code == df_leagues.code,
    "left"
).drop("code")

w = Window.partitionBy("match_id").orderBy(col("ingestion_ts").desc())
df_silver_dedup = df_enriched.withColumn("rn", row_number().over(w)) \
                             .filter(col("rn") == 1) \
                             .drop("rn")

df_silver_dedup.cache()

if DeltaTable.isDeltaTable(spark, path_silver):
    deltaTable = DeltaTable.forPath(spark, path_silver)
    
    (deltaTable.alias("target")
        .merge(
            df_silver_dedup.alias("source"),
            "target.match_id = source.match_id"
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
else:
    df_silver_dedup.coalesce(1).write.format("delta").mode("overwrite").save(path_silver)

# CAMADA OURO
df_silver_dedup.createOrReplaceTempView("view_silver_dedup")

df_gold = spark.sql("""
    SELECT 
        league_name,
        DATE(match_timestamp_br) as match_day,
        COUNT(match_id) as total_matches,
        SUM(coalesce(score_home, 0) + coalesce(score_away, 0)) as total_goals,
        ROUND(AVG(coalesce(score_home, 0) + coalesce(score_away, 0)), 2) as avg_goals_match
    FROM view_silver_dedup
    GROUP BY 
        league_name, 
        DATE(match_timestamp_br)
    ORDER BY 
        match_day DESC
""")

condition_replace = f"match_day = '{data_filtro_iso}'"

df_gold.coalesce(1).write \
       .format("delta") \
       .mode("overwrite") \
       .option("replaceWhere", condition_replace) \
       .save(gold_path)

df_silver_dedup.unpersist()

# LIMPEZA DE ARQUIVOS
def clean_ghost_files(bucket, prefix):
    s3 = boto3.resource('s3')
    bucket_obj = s3.Bucket(bucket)
    for obj in bucket_obj.objects.filter(Prefix=prefix):
        if obj.key.endswith("_$folder$"):
            obj.delete()

try:
    clean_ghost_files(bucket_name, "bronze")
    clean_ghost_files(bucket_name, "silver")
    clean_ghost_files(bucket_name, "gold")
except Exception as e:
    print(f"Aviso: Não foi possível limpar arquivos fantasmas: {e}")

job.commit()