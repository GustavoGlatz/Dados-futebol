# Imagem Base Oficial da AWS para Lambda Python
FROM public.ecr.aws/lambda/python:3.11

# dependências
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt

# Copiar o código para a pasta raiz da tarefa
COPY main.py ${LAMBDA_TASK_ROOT}

# Definir o comando (CMD) apontando para a função handler
# Sintaxe: nome_do_arquivo.nome_da_funcao
CMD [ "main.lambda_handler" ]