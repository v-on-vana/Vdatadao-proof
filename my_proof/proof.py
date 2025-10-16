# vdatadao proof generation system - modular architecture for instagram & google data validation

import logging
import os
from datetime import datetime, timezone

from my_proof.models.proof_response import ProofResponse
from my_proof.utils.schema import validate_schema
from my_proof.processors.instagram_processor import InstagramProcessor
from my_proof.processors.google_processor import GoogleProcessor
from my_proof.validators.duplicate_validator import DuplicateValidator
from my_proof.config import settings

class Proof:
    # Ana proof class'ı - tüm validation işlemleri burada yapılıyor
    
    def __init__(self):
        # Başlangıç ayarları - response objesi ve validator'ları hazırlıyoruz
        self.proof_response = ProofResponse(dlp_id=settings.DLP_ID)
        self.duplicate_validator = DuplicateValidator()  # sahte veri kontrol edici
        
    def generate(self) -> ProofResponse:
        # ANA FONKSİYON - Burda tüm validation süreci işliyor
        # 5 aşamalı kontrol sistemi ile çalışıyor
        logging.info("Starting proof generation for vdatadao with improved validation flow")
        errors = []
        
        all_files = os.listdir(settings.INPUT_DIR)
        logging.info(f"Found {len(all_files)} files in input directory: {all_files}")
        
        json_files = [f for f in all_files if f.lower().endswith('.json')]
        logging.info(f"Found {len(json_files)} JSON files: {json_files}")
        
        if len(json_files) == 0:
            logging.error("No JSON files found in input directory!")
            errors.append("NO_JSON_FILES_FOUND")
            self.proof_response.attributes["errors"] = errors
            self.proof_response.valid = False
            return self.proof_response

        # Input klasöründeki JSON dosyalarını tek tek işle
        for input_filename in all_files:
            input_file = os.path.join(settings.INPUT_DIR, input_filename)

            if os.path.splitext(input_file)[1].lower() == ".json":
                logging.info(f"Processing JSON file: {input_filename}")
                
                # Dosyayı yükle ve parse et
                input_data = self._load_and_validate_file(input_file, errors)
                if not input_data:
                    logging.error(f"Failed to load data from {input_filename}")
                    continue
                
                logging.info(f"Successfully loaded JSON data from {input_filename}")
                
                # Temel bilgileri çıkar - bunlar olmadan işlem yapamayız
                contributor_email = input_data.get('contributor', {}).get('email')
                wallet_address = input_data.get('contributor', {}).get('wallet_address')
                
                if not contributor_email or not wallet_address:
                    errors.append("MISSING_CONTRIBUTOR_INFO")
                    logging.error("Missing contributor email or wallet address")
                    break
                
                # AŞAMA 1: ŞEMA KONTROLÜ - BYPASSED (tüm veri yapıları kabul ediliyor)
                logging.info("Step 1: Schema validation (bypassed)")
                schema_type, schema_matches = validate_schema(input_data)

                # AŞAMA 2: DUPLICATE DATA KONTROLÜ - en kritik kısım!
                # Wallet, email, veri hash, aktivite parmak izi hepsi kontrol ediliyor
                logging.info("Step 2: Duplicate data validation")
                is_duplicate, duplicate_reason = self.duplicate_validator.check_for_duplicate_data(
                    input_data, wallet_address, contributor_email
                )
                if is_duplicate:
                    errors.append(f"DUPLICATE_DATA: {duplicate_reason}")
                    logging.error(f"Duplicate data detected: {duplicate_reason}")
                    break

                # AŞAMA 3: HAM VERİ KONTROLÜ
                # Raw export data yeterli mi? boyutu uygun mu?
                logging.info("Step 3: Raw data validation")
                if not self._validate_raw_export_data_simple(input_data, errors):
                    logging.error("Raw data validation failed")
                    break

                # AŞAMA 4: VERİ İŞLEME VE SKORLAMA
                # Instagram/Google işlemcisi ile veriler analiz ediliyor
                logging.info("Step 4: Processing data and calculating scores")
                self._process_data_by_type(input_data, schema_type, schema_matches, errors)
                
                # AŞAMA 5: DATABASE'E KAYDETME (sadece hata yoksa)
                # Geçerli veriyi kalıcı olarak saklıyoruz
                if len(errors) == 0:
                    logging.info("Step 5: Saving valid data to database")
                    data_saved = self.duplicate_validator.register_valid_data(input_data, wallet_address, contributor_email)
                    
                    if not data_saved:
                        logging.warning("Failed to save data to database")

                self.proof_response.metadata = {
                    "schema_type": schema_type,
                    "validation_steps_completed": 5,
                    "duplicate_check_reason": duplicate_reason if is_duplicate else "NO_DUPLICATE"
                }

                self.proof_response.valid = len(errors) == 0
                logging.info(f"Proof generation completed with {len(errors)} errors")

        if len(errors) > 0:
            self.proof_response.attributes["errors"] = errors
            logging.error(f"Proof generation failed with errors: {errors}")

        return self.proof_response

    def _load_and_validate_file(self, input_file, errors):
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                json_content = f.read()
                logging.info(f"Validating file: {json_content[:50]}...")
                import json
                return json.loads(json_content)
        except Exception as e:
            logging.error(f"Error loading file {input_file}: {str(e)}")
            errors.append("FILE_LOADING_ERROR")
            return None


    def _validate_raw_export_data_simple(self, input_data, errors):
        # Ham Instagram/Google export verisinin yeterli olup olmadığını kontrol ediyor
        # Sahte minimal verilerle gelen submission'ları engellemek için
        try:
            data_section = input_data.get('data', {})
            profile = data_section.get('profile', {})
            
            # 1. Profil temel kontrolü - username ve email olmadan olmaz
            if not profile.get('username') or not profile.get('email'):
                errors.append("MISSING_BASIC_PROFILE_DATA")
                return False
                
            # 2. Raw export data varlık kontrolü - asıl veriler burada
            raw_export_data = data_section.get('raw_export_data', {})
            if not raw_export_data:
                errors.append("MISSING_RAW_EXPORT_DATA")
                return False
                
            # 3. Kategori sayısı kontrolü - çok az kategori varsa şüpheli
            category_count = len(raw_export_data)
            if category_count < 3:
                errors.append("INSUFFICIENT_RAW_DATA_CATEGORIES")
                logging.warning(f"Raw data has only {category_count} categories, minimum 3 required")
                return False
                
            # 4. İçerik boyutu hesaplama
            total_content_size = 0
            categories_with_content = 0
            
            for category_name, category_data in raw_export_data.items():
                if isinstance(category_data, dict) and 'content' in category_data:
                    content = category_data['content']
                    if content:  # İçerik boş değilse say
                        content_size = len(str(content))
                        total_content_size += content_size
                        categories_with_content += 1
                        
            # 5. Minimum boyut kontrolü - çok küçük data sahte olabilir
            min_required_size = 500
            if total_content_size < min_required_size:
                errors.append("INSUFFICIENT_RAW_DATA_SIZE")
                logging.warning(f"Raw data size {total_content_size} bytes, minimum {min_required_size} required")
                return False
                
            # 6. İçerikli kategori kontrolü - en az 2 kategori dolu olmalı
            if categories_with_content < 2:
                errors.append("INSUFFICIENT_CONTENT_CATEGORIES")
                logging.warning(f"Only {categories_with_content} categories have content, minimum 2 required")
                return False
                
            logging.info(f"Raw export validation passed: {category_count} categories, {categories_with_content} with content, {total_content_size:,} bytes total")
            return True
            
        except Exception as e:
            logging.error(f"Error in raw export data validation: {str(e)}")
            errors.append("RAW_EXPORT_VALIDATION_ERROR")
            return False

    def _process_data_by_type(self, input_data, schema_type, schema_matches, errors):
        # Veri tipine göre doğru işlemciyi seç - Instagram vs Google
        # Her platform'un kendine özel analiz yöntemi var
        if schema_type == "instagram-meta-export.json":
            processor = InstagramProcessor(self.proof_response)
            processor.process_data(input_data, schema_matches, errors)
        else:
            processor = GoogleProcessor(self.proof_response)
            processor.process_data(input_data, schema_matches, errors)

