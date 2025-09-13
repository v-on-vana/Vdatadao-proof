import sqlite3
import os

db_path = "data/registry.db"

if not os.path.exists(db_path):
    print("Database yok!")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=== EMAIL REGISTRY ===")
    cursor.execute("SELECT * FROM email_registry")
    emails = cursor.fetchall()
    if emails:
        for row in emails:
            print(f"ID: {row[0]}, Email Hash: {row[1][:16]}..., Wallet: {row[2][:10]}..., Tarih: {row[3]}")
    else:
        print("Email kayıt yok")
    
    print("\n=== WALLET REGISTRY ===")
    cursor.execute("SELECT * FROM wallet_registry")
    wallets = cursor.fetchall()
    if wallets:
        for row in wallets:
            print(f"ID: {row[0]}, Wallet: {row[1][:10]}..., Email: {row[2][:16]}..., Data: {row[3][:16]}..., Platform: {row[4]}, Tarih: {row[5]}")
    else:
        print("Wallet kayıt yok")
    
    print("\n=== DATA HASH REGISTRY ===")
    cursor.execute("SELECT * FROM data_hash_registry")
    datas = cursor.fetchall()
    if datas:
        for row in datas:
            print(f"ID: {row[0]}, Data: {row[1][:16]}..., Fingerprint: {row[2][:16]}..., Wallet: {row[3][:10]}..., Email: {row[4][:16]}..., Contribution: {row[5]}, Platform: {row[6]}, Tarih: {row[7]}")
    else:
        print("Data kayıt yok")
    
    print(f"\nToplam Boyut: {os.path.getsize(db_path)} byte")
    conn.close()
