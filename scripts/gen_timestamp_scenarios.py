import json, time, hashlib, random
from datetime import datetime

now = int(time.time())
iso = lambda t: datetime.fromtimestamp(t).isoformat()

def big_blob(n):
    return {'content': {'blob': 'x'*n}}

def base_doc():
    ts = int(time.time())
    email = f'ts_test_{ts}_{random.randint(1000,9999)}@example.com'
    wallet = '0x' + hashlib.sha256(f'{ts}_{random.random()}'.encode()).hexdigest()[:40]
    return {
      'contribution_id': f'meta_export_{ts}',
      'contributor': {'email': email, 'wallet_address': wallet, 'name': 'TS User', 'locale': 'en'},
      'data': {
        'platform': 'instagram',
        'source_type': 'meta_export',
        'extraction_method': 'google_drive_api',
        'profile': {'username': f'ts_user_{ts}', 'display_name': 'TS User', 'email': email, 'account_type': 'Public', 'phone_confirmed': False, 'private_account': False},
        'metrics': {'posts_count': 5, 'following_count': 10, 'follower_count': 20, 'likes_given_count': 15, 'comments_count': 8, 'account_age_days': 500, 'total_interactions': 23, 'has_story_activity': True},
        'activities': {'following_list': [], 'likes_given': [], 'posts_created': [], 'comments_made': []},
        'security': {'last_login': ts, 'contact_syncing': False, 'has_shared_live_video': False},
        'raw_export_data': {
          'personal_information': big_blob(25000),
          'profile_information': big_blob(25000),
          'profile_changes': big_blob(25000),
          'liked_posts': big_blob(50000),
          'comments': big_blob(25000),
          'profile_photos': big_blob(5000)
        }
      },
      'metadata': {
        'version': '1.0.0', 'schema_version': 'vana_datadao_v1', 'source': 'TS Scenarios',
        'collection_date': iso(ts), 'data_type': 'instagram_meta_export', 'processing_timestamp': ts,
        'extraction_completeness': 85.0,
        'folder_structure': {'metaFolderId':'meta','instagramFolderId':'ig','instagramFolderName':'ig-folder'},
        'privacy_settings': {'contains_pii': True, 'anonymization_level': 'partial', 'retention_policy':'user_controlled'},
        'quality_score': 90.0, 'data_freshness': 75.0
      },
      'created_at': iso(ts), 'updated_at': iso(ts)
    }

# Scenario A: Regular intervals in posts + contribution_id ending with '000' + future ms processing_timestamp
A = base_doc()
start = now - 3600
interval = 600
A['data']['activities']['posts_created'] = [{'creation_timestamp': start + i*interval, 'title': f'P{i}'} for i in range(6)]
A['contribution_id'] = f"meta_export_{str(now)}000"
A['metadata']['processing_timestamp'] = int((now + 86400) * 1000)  # future (ms)
open('input/ts_regular_intervals.json','w').write(json.dumps(A, indent=2))

# Scenario B: Future processing_timestamp by 1 day (ms)
B = base_doc()
B['metadata']['processing_timestamp'] = int((now + 86400) * 1000)
open('input/ts_future_processing.json','w').write(json.dumps(B, indent=2))

# Scenario C: collection_date and processing_timestamp mismatch (>1h)
C = base_doc()
C['metadata']['collection_date'] = iso(now)
C['metadata']['processing_timestamp'] = int((now - 2*3600) * 1000)  # 2 hours earlier (ms)
open('input/ts_mismatch_collection.json','w').write(json.dumps(C, indent=2))

# Scenario D: Very small account_age_days with many posts -> high posts/day
D = base_doc()
D['data']['metrics']['account_age_days'] = 1
D['data']['metrics']['posts_count'] = 50
D['data']['activities']['posts_created'] = [{'creation_timestamp': now - i*60, 'title': f'Burst{i}'} for i in range(50)]
open('input/ts_high_post_rate.json','w').write(json.dumps(D, indent=2))

print('✅ Timestamp senaryoları oluşturuldu')
