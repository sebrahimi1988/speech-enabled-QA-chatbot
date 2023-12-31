# Databricks notebook source
# MAGIC %md
# MAGIC ##Log the Whisper Large V2 Model to Mlflow Registry
# MAGIC
# MAGIC **ATTENTION** You need a single-GPU cluster such as g5.8xlarge (on AWS) to run this code. 

# COMMAND ----------

# MAGIC %pip install torch

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import pandas as pd
import numpy as np
import transformers
import mlflow
import torch
from datasets import load_dataset

# COMMAND ----------

# Download the Whisper model snapshot from huggingface
from huggingface_hub import snapshot_download
snapshot_location = snapshot_download(repo_id="openai/whisper-large-v2", ignore_patterns=["*.msgpack", "*.h5"])

# COMMAND ----------

# Define custom Python model class
class Whisper(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
      repository = context.artifacts['repository']
      self.processor = transformers.WhisperProcessor.from_pretrained(repository)
      self.model = transformers.WhisperForConditionalGeneration.from_pretrained(
          repository, low_cpu_mem_usage=True, device_map="auto")
      self.model.config.forced_decoder_ids = None
      self.model.to('cuda').eval()

    def predict(self, context, model_input):
      audio = model_input["audio"] 
      sampling_rate = model_input["sampling_rate"][0]
      with torch.no_grad():
          input_features = self.processor(audio, sampling_rate=sampling_rate, return_tensors='pt').input_features.to('cuda')
          predicted_ids = self.model.generate(input_features).to('cuda')
      return self.processor.batch_decode(predicted_ids, skip_special_tokens=True)

# COMMAND ----------

from mlflow.models.signature import ModelSignature
from mlflow.types import DataType, Schema, ColSpec
from mlflow.models.signature import infer_signature

# Define input example
ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation")
sample = ds[0]["audio"]
input_example=pd.DataFrame({
            "audio":sample["array"], 
            "sampling_rate": sample["sampling_rate"]})
signature = infer_signature(input_example, "some random text")

# Log the model with its details such as artifacts, pip requirements and input example
user_name = dbutils.notebook.entry_point.getDbutils().notebook().getContext().userName().get()


mlflow.create_experiment(f"/Users/{user_name}/whisper")
mlflow.set_experiment(f"/Users/{user_name}/whisper")
with mlflow.start_run() as run:  
    mlflow.pyfunc.log_model(
        "model",
        python_model=Whisper(),
        artifacts={'repository' : snapshot_location},
        pip_requirements=["torch", "transformers", "accelerate"],
        input_example=input_example,
        signature=signature,
    )

# COMMAND ----------

# Register model in MLflow Model Registry
result = mlflow.register_model(
    "runs:/"+run.info.run_id+"/model",
    "whisper-cmt"
)

# COMMAND ----------

# Load the logged model
loaded_model = mlflow.pyfunc.load_model("runs:/"+run.info.run_id+"/model")

# COMMAND ----------

# Make a prediction using the loaded model
loaded_model.predict(input_example)
