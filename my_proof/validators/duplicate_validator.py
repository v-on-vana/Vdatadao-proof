import hashlib
import json
import logging
from typing import Dict, Any, Tuple

from my_proof.utils.db import DataRegistry, hash_email
from my_proof.config import settings

class DuplicateValidator:
    # Bu class sahte/tekrar veri tespiti yapıyor - en önemli güvenlik kısmı
    
    def __init__(self):
        # Database bağlantısı kuruyoruz, yoksa çalışmaz
        try:
            self.data_registry = DataRegistry()
            self.db_available = True
        except Exception as e:
            logging.error(f"Data registry initialization failed: {str(e)}")
            self.db_available = False
        
        # Hash cache - performance için aynı hash'leri tekrar hesaplamayız
        self._cached_hashes = None
    
    def check_for_duplicate_data(self, input_data: Dict[str, Any], wallet_address: str, contributor_email: str) -> Tuple[bool, str]:
        # Ana kontrol fonksiyonu - burda her şey kontrol ediliyor
        # wallet + email + veri kombinasyonu hiç görülmüşmü diye bakıyoruz
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping duplicate data check")
                return False, "DATABASE_UNAVAILABLE"
            
            # Önce verinin hash'ini ve parmak izini çıkarıyoruz
            data_hash = self.calculate_data_hash(input_data)  # tüm veri için hash
            fingerprint = self._generate_core_data_fingerprint(input_data)  # aktivite parmak izi
            email_hash = hash_email(contributor_email)  # email hash'i
            
            if not data_hash or not fingerprint:
                logging.error("Failed to generate data hash or fingerprint")
                return False, "HASH_GENERATION_ERROR"
            
            # Hash'leri cache'liyoruz - register_valid_data'da tekrar kullanmak için
            self._cached_hashes = {
                'data_hash': data_hash,
                'fingerprint': fingerprint,
                'email_hash': email_hash
            }
            
            # Asıl kontrolü database'de yapıyoruz - ultra sıkı kurallar
            is_duplicate, reason = self.data_registry.check_data_duplicate(
                data_hash, fingerprint, wallet_address, email_hash
            )
            
            if is_duplicate:
                logging.warning(f"Duplicate data detected for {wallet_address[:10]}...: {reason}")
                return True, reason
            
            logging.info(f"No duplicate found for {wallet_address[:10]}...: {reason}")
            return False, reason
            
        except Exception as e:
            logging.error(f"Error checking for duplicate data: {str(e)}")
            return False, f"ERROR: {str(e)}"

    def calculate_data_hash(self, input_data: Dict[str, Any]) -> str:
        # Gelen verinin SHA256 hash'ini hesaplıyoruz - tekrar veri tespiti için kullanılacak
        try:
            normalized_data = json.loads(json.dumps(input_data))
            
            # Bu alanları hash'e dahil etmiyoruz çünkü her seferinde değişiyorlar
            fields_to_exclude = [
                'created_at', 'updated_at', 'processing_timestamp',
                'collection_date', 'metadata.processing_timestamp',
                'metadata.collection_date', 'data.raw_export_data'
            ]
            
            # Gereksiz alanları temizliyoruz
            for field_path in fields_to_exclude:
                self._remove_nested_field(normalized_data, field_path)
            
            data_size = len(str(normalized_data))
            logging.info(f"Normalizing data for hash (size: {data_size} chars)")
            
            # JSON'u normalize edip SHA256 hash alıyoruz
            normalized_json = json.dumps(normalized_data, sort_keys=True, separators=(',', ':'))
            data_hash = hashlib.sha256(normalized_json.encode('utf-8')).hexdigest()
            
            logging.info(f"Calculated data hash: {data_hash[:16]}...")
            return data_hash
            
        except (MemoryError, UnicodeError) as e:
            logging.error(f"Memory/encoding error in hash calculation: {str(e)}")
            return self._calculate_simple_hash(input_data)  # hata olursa basit hash kullan
        except Exception as e:
            logging.error(f"Error calculating data hash: {str(e)}")
            return self._calculate_simple_hash(input_data)

    def is_duplicate_data(self, current_hash: str) -> bool:
        """
        Check if a data hash already exists in the database.
        
        Args:
            current_hash: SHA256 hash of the data to check
            
        Returns:
            bool: True if hash exists, False otherwise
        """
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping hash check")
                return False
            
            is_registered, registered_wallet, registered_email = self.data_registry.is_data_hash_registered(current_hash)
            
            if is_registered:
                logging.info(f"Hash {current_hash[:16]}... found in database: wallet {registered_wallet[:10] if registered_wallet else 'unknown'}...")
                return True
            
            logging.info(f"Hash {current_hash[:16]}... not found in database")
            return False
            
        except Exception as e:
            logging.error(f"Error checking for duplicate data: {str(e)}")
            return False

    def _generate_core_data_fingerprint(self, input_data: Dict[str, Any]) -> str:
        # EN ÖNEMLİ FONKSİYON! Sahte veri tespiti burada yapılıyor
        # Following, post, beğeni aktivitelerine bakıyoruz - profil bilgisi değil
        try:
            data_section = input_data.get('data', {})
            activities = data_section.get('activities', {})
            
            # Aktivite bazlı parmak izi - profil bağımsız
            activity_fingerprint = {}
            
            # Takip listesi imzası - sahte takip listelerini engelliyor
            following_list = activities.get('following_list', [])
            if following_list and len(following_list) >= 3:
                # TÜM takip edilenlerin imzasını alıyoruz - güçlü tespit için
                following_signature = []
                for follow in following_list:  # tüm following verisini dahil et
                    if follow.get('username') and follow.get('followed_at'):
                        following_signature.append({
                            'username': follow.get('username'),  # kimi takip etmiş
                            'followed_at': follow.get('followed_at')  # ne zaman takip etmiş
                        })
                activity_fingerprint['following_signature'] = following_signature
            
            # Post imzası - sahte post verilerini engelliyor
            posts_created = activities.get('posts_created', [])
            if posts_created:
                posts_signature = []
                for post in posts_created:  # tüm postları al
                    if post.get('creation_timestamp'):
                        posts_signature.append({
                            'creation_timestamp': post.get('creation_timestamp'),  # post zamanı
                            'title': post.get('title', ''),  # post başlığı
                            'source_app': post.get('source_app'),  # hangi uygulamadan
                            'has_photo': post.get('has_photo'),  # fotoğraf varmı
                            'has_camera_metadata': post.get('has_camera_metadata')  # kamera bilgisi
                        })
                activity_fingerprint['posts_signature'] = posts_signature
            
            # Beğeni imzası - sahte beğeni verilerini engelliyor
            likes_given = activities.get('likes_given', [])
            if likes_given:
                likes_signature = []
                for like in likes_given:
                    likes_signature.append({
                        'target_username': like.get('target_username'),  # kimi beğenmiş
                        'count': like.get('count'),  # kaç kez
                        'last_activity': like.get('last_activity')  # son aktivite
                    })
                activity_fingerprint['likes_signature'] = likes_signature
            
            # Yorum imzası - sahte yorum tespiti
            comments_made = activities.get('comments_made', [])
            if comments_made:
                comments_signature = []
                for comment in comments_made:
                    if comment.get('timestamp'):
                        comments_signature.append({
                            'timestamp': comment.get('timestamp'),  # yorum zamanı
                            'content': comment.get('content', '')[:20]  # ilk 20 karakter
                        })
                activity_fingerprint['comments_signature'] = comments_signature
            
            # Eğer önemli aktivite yoksa temel profili kullan
            if not activity_fingerprint:
                profile = data_section.get('profile', {})
                activity_fingerprint = {
                    'username': profile.get('username'),
                    'account_type': profile.get('account_type')
                }
            
            # Aktivite parmak izini hash'e çevir
            fingerprint_json = json.dumps(activity_fingerprint, sort_keys=True, separators=(',', ':'))
            fingerprint_hash = hashlib.sha256(fingerprint_json.encode('utf-8')).hexdigest()
            
            logging.info(f"Generated activity fingerprint: {fingerprint_hash[:16]}... from {len(activity_fingerprint)} activity types")
            return fingerprint_hash
            
        except Exception as e:
            logging.error(f"Error generating activity fingerprint: {str(e)}")
            return ""

    def _calculate_data_similarity(self, current_fingerprint: str, existing_hash: str) -> float:
        try:
            if current_fingerprint == existing_hash:
                return 1.0
                
            current_bytes = bytes.fromhex(current_fingerprint) if len(current_fingerprint) == 64 else current_fingerprint.encode()
            existing_bytes = bytes.fromhex(existing_hash) if len(existing_hash) == 64 else existing_hash.encode()
            
            matching_bits = sum(a == b for a, b in zip(current_bytes, existing_bytes))
            total_bits = max(len(current_bytes), len(existing_bytes))
            
            similarity = matching_bits / total_bits if total_bits > 0 else 0.0
            
            if similarity > 0.7:
                logging.info(f"Data similarity detected: {similarity:.2f}")
                
            return similarity
            
        except Exception as e:
            logging.error(f"Error calculating data similarity: {str(e)}")
            return 0.0

    def _remove_nested_field(self, data: Dict[str, Any], field_path: str) -> None:
        try:
            keys = field_path.split('.')
            current_level = data
            
            for key in keys[:-1]:
                if isinstance(current_level, dict) and key in current_level:
                    current_level = current_level[key]
                else:
                    return
            
            if isinstance(current_level, dict) and keys[-1] in current_level:
                del current_level[keys[-1]]
                logging.debug(f"Removed field: {field_path}")
                
        except (KeyError, TypeError, AttributeError):
            pass

    def _calculate_simple_hash(self, input_data: Dict[str, Any]) -> str:
        try:
            profile = input_data.get('data', {}).get('profile', {})
            
            core_data = {
                'contribution_id': input_data.get('contribution_id'),
                'contributor': input_data.get('contributor', {}),
                'data': {
                    'platform': input_data.get('data', {}).get('platform'),
                    'profile': {
                        'username': profile.get('username'),
                        'email': hashlib.sha256(str(profile.get('email', '')).encode('utf-8')).hexdigest(),
                        'account_type': profile.get('account_type')
                    }
                }
            }
            
            core_json = json.dumps(core_data, sort_keys=True, separators=(',', ':'))
            simple_hash = hashlib.sha256(core_json.encode('utf-8')).hexdigest()
            
            logging.info(f"Using simple hash calculation: {simple_hash[:16]}...")
            return simple_hash
            
        except Exception as e:
            logging.error(f"Simple hash calculation failed: {str(e)}")
            fallback_data = input_data.get('contribution_id', str(input_data))
            return hashlib.sha256(str(fallback_data).encode('utf-8')).hexdigest()

    def _check_wallet_email_binding(self, wallet_address: str, contributor_email: str) -> bool:
        try:
            if not contributor_email or not self.db_available:
                return False
                
            email_hash = hash_email(contributor_email)
            is_registered, registered_wallet = self.data_registry.is_email_hash_registered(email_hash)
            
            if is_registered and registered_wallet and str(registered_wallet).lower() != str(wallet_address).lower():
                logging.warning(f"Email {contributor_email[:10]}... already registered to different wallet {str(registered_wallet)[:10]}...")
                return True
            
            if not is_registered:
                self.data_registry.register_email_hash(email_hash, wallet_address)
                
            return False
            
        except Exception as e:
            logging.error(f"Error checking wallet-email binding: {str(e)}")
            return False

    def register_valid_data(self, input_data: Dict[str, Any], wallet_address: str, contributor_email: str) -> bool:
        # Başarılı geçen veriyi database'e kayıt ediyoruz
        # Wallet + veri hash + parmak izi hepsini saklıyoruz ki sonra kontrol edebilelim
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping data registration")
                return False
            
            # Cache'den hash'leri al - tekrar hesaplamak yerine (PERFORMANCE İYİLEŞTİRMESİ!)
            if hasattr(self, '_cached_hashes') and self._cached_hashes:
                data_hash = self._cached_hashes['data_hash']
                fingerprint = self._cached_hashes['fingerprint']
                email_hash = self._cached_hashes['email_hash']
                logging.info("Using cached hashes for registration (performance optimization)")
            else:
                # Cache yoksa tekrar hesapla (fallback)
                logging.warning("No cached hashes found, recalculating...")
                data_hash = self.calculate_data_hash(input_data)
                fingerprint = self._generate_core_data_fingerprint(input_data)
                email_hash = hash_email(contributor_email)
            
            if not data_hash or not fingerprint:
                logging.error("Failed to generate data hash or fingerprint for registration")
                return False
            
            contribution_id = input_data.get('contribution_id')
            platform = input_data.get('data', {}).get('platform', 'instagram')
            
            # Önce wallet'ı kaydet (bu wallet'ın ilk submission'ı olduğu için)
            wallet_success = self.data_registry.register_wallet(
                wallet_address, email_hash, data_hash, platform
            )
            
            # Sonra veri hash'ini kaydet
            data_success = self.data_registry.register_data_hash(
                data_hash, fingerprint, wallet_address, email_hash, contribution_id, platform
            )
            
            # Cache'i temizle - bir sonraki submission için
            if hasattr(self, '_cached_hashes'):
                delattr(self, '_cached_hashes')
            
            if wallet_success and data_success:
                logging.info(f"Successfully registered wallet and data for {wallet_address[:10]}...")
                return True
            else:
                logging.error(f"Failed to register wallet or data for {wallet_address[:10]}... (wallet: {wallet_success}, data: {data_success})")
                return False
            
        except Exception as e:
            logging.error(f"Error registering valid data: {str(e)}")
            return False

    def validate_raw_export_data(self, input_data: Dict[str, Any]) -> tuple:
        try:
            data_section = input_data.get('data', {})
            
            if not data_section.get('raw_export_data'):
                return False, ["MISSING_RAW_EXPORT_DATA"], 0.0
            
            required_sections = ['profile', 'activities', 'metrics']
            required_fields = ['username', 'email', 'account_type', 'posts_count', 'following_count', 'follower_count']
            
            found_fields = 0
            total_required = len(required_fields)
            
            profile = data_section.get('profile', {})
            activities = data_section.get('activities', {})
            metrics = data_section.get('metrics', {})
            
            if profile.get('username'): found_fields += 1
            if profile.get('email'): found_fields += 1  
            if profile.get('account_type'): found_fields += 1
            if metrics.get('posts_count') is not None: found_fields += 1
            if metrics.get('following_count') is not None: found_fields += 1
            if metrics.get('follower_count') is not None: found_fields += 1
            
            completeness_score = (found_fields / total_required) * 100.0
            is_valid = completeness_score >= 70.0
            
            return is_valid, [], completeness_score
            
        except Exception as e:
            logging.error(f"Error validating raw export data: {str(e)}")
            return False, ["RAW_EXPORT_VALIDATION_ERROR"], 0.0
