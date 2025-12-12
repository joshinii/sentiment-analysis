from optimum.onnxruntime import ORTModelForSequenceClassification
from transformers import AutoTokenizer
import os

model_id = "distilbert-base-uncased-finetuned-sst-2-english"
output_dir = "backend/model_assets"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

print(f"Exporting {model_id} to {output_dir}...")
model = ORTModelForSequenceClassification.from_pretrained(model_id, export=True)
tokenizer = AutoTokenizer.from_pretrained(model_id)

model.save_pretrained(output_dir)
tokenizer.save_pretrained(output_dir)
print("Export complete.")
