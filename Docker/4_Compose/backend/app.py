from fastapi import FastAPI
import psycopg2
import os

app = FastAPI()

@app.get("/")
def root():
    return {"status": "yoooooooooo"}

@app.get("/db")
def check_db():
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )
    conn.close()
    return {"db": "connected"}