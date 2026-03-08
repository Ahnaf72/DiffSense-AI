import mysql.connector

def get_db():
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",  # add your MySQL password
        database="ai_diff_checker"
    )
    return db