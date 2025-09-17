#!/usr/bin/env python3

import os
import sys
import subprocess
import json
from pathlib import Path

def setup_environment():
    """PostgreSQL bağlantı ayarlarını yapılandır"""
    print("🔧 PostgreSQL bağlantı ayarları yapılandırılıyor...")
    
    password = input("PostgreSQL şifrenizi girin: ")
    
    os.environ['DB_HOST'] = 'vdt.cr.vdatadao.xyz'
    os.environ['DB_PORT'] = '5432'
    os.environ['DB_NAME'] = 'postgres'
    os.environ['DB_USER'] = 'postgres'
    os.environ['DB_PASSWORD'] = password
    
    os.environ['INPUT_DIR'] = 'demo/input'
    os.environ['OUTPUT_DIR'] = 'output'
    os.environ['DLP_ID'] = '143'
    os.environ['DLP_CONTRACT_ADDRESS'] = '0xaA45d51168BB94CC7b7402bb051159276b6279b2'
    os.environ['RPC_URL'] = 'https://rpc.moksha.vana.org'
    os.environ['FILE_ID'] = '0'
    os.environ['DOCKER_CONTAINER'] = 'false'
    
    print("✅ Environment variables ayarlandı")

def create_output_directory():
    """Output klasörünü oluştur"""
    output_dir = Path('output')
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"✅ Output klasörü oluşturuldu: {output_dir.absolute()}")
    else:
        print(f"✅ Output klasörü mevcut: {output_dir.absolute()}")

def test_database_connection():
    """PostgreSQL bağlantısını test et"""
    print("\n🔍 PostgreSQL bağlantısı test ediliyor...")
    
    try:
        from sqlalchemy import create_engine, text
        
        db_host = os.environ['DB_HOST']
        db_port = os.environ['DB_PORT']
        db_name = os.environ['DB_NAME']
        db_user = os.environ['DB_USER']
        db_password = os.environ['DB_PASSWORD']
        
        database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        
        engine = create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
        
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ PostgreSQL bağlantısı başarılı!")
            print(f"   Version: {version[:50]}...")
            
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL bağlantı hatası: {e}")
        return False

def check_input_files():
    """Input dosyalarını kontrol et"""
    print("\n📂 Input dosyaları kontrol ediliyor...")
    
    input_dir = Path('demo/input')
    if not input_dir.exists():
        print(f"❌ Input klasörü bulunamadı: {input_dir}")
        return False
    
    json_files = list(input_dir.glob('*.json'))
    if not json_files:
        print(f"❌ Input klasöründe JSON dosyası bulunamadı: {input_dir}")
        return False
    
    for json_file in json_files:
        print(f"✅ Input dosyası bulundu: {json_file.name} ({json_file.stat().st_size} bytes)")
    
    return True

def run_proof_generation():
    """Proof generation işlemini başlat"""
    print("\n🚀 Proof generation başlatılıyor...")
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'my_proof'
        ], capture_output=True, text=True, cwd=os.getcwd())
        
        print("📤 STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("📤 STDERR:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ Proof generation tamamlandı!")
            return True
        else:
            print(f"❌ Proof generation başarısız! Return code: {result.returncode}")
            return False
            
    except Exception as e:
        print(f"❌ Proof generation hatası: {e}")
        return False

def check_results():
    """Sonuçları kontrol et ve göster"""
    print("\n📊 Sonuçlar kontrol ediliyor...")
    
    results_file = Path('output/results.json')
    
    if not results_file.exists():
        print(f"❌ Sonuç dosyası bulunamadı: {results_file}")
        return False
    
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        print(f"✅ Sonuç dosyası bulundu: {results_file}")
        print(f"📄 Dosya boyutu: {results_file.stat().st_size} bytes")
        
        print("\n📋 Proof Sonuçları:")
        print(f"   DLP ID: {results.get('dlp_id', 'N/A')}")
        print(f"   Valid: {results.get('valid', 'N/A')}")
        print(f"   Score: {results.get('score', 'N/A')}")
        print(f"   Authenticity: {results.get('authenticity', 'N/A')}")
        print(f"   Ownership: {results.get('ownership', 'N/A')}")
        print(f"   Quality: {results.get('quality', 'N/A')}")
        print(f"   Uniqueness: {results.get('uniqueness', 'N/A')}")
        
        if results.get('attributes'):
            print("\n📝 Attributes:")
            for key, value in results['attributes'].items():
                print(f"   {key}: {value}")
        
        if results.get('errors'):
            print(f"\n⚠️  Errors: {results['errors']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Sonuç dosyası okuma hatası: {e}")
        return False

def main():
    """Ana test fonksiyonu"""
    print("🔬 VDataDAO Proof System Test Script")
    print("=" * 50)
    
    setup_environment()
    
    create_output_directory()
    
    if not test_database_connection():
        print("\n❌ Test durduruldu: PostgreSQL bağlantısı başarısız!")
        return False
    
    if not check_input_files():
        print("\n❌ Test durduruldu: Input dosyaları bulunamadı!")
        return False
    
    if not run_proof_generation():
        print("\n❌ Test durduruldu: Proof generation başarısız!")
        return False
    
    if not check_results():
        print("\n❌ Test durduruldu: Sonuçlar kontrol edilemedi!")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 TÜM TESTLER BAŞARILI!")
    print("✅ Proof sistemi düzgün çalışıyor!")
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Test kullanıcı tarafından durduruldu!")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Beklenmeyen hata: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
