import psycopg2

regions = [
    'aws-0-us-east-1',
    'aws-0-us-west-1', 
    'aws-0-eu-west-1',
    'aws-0-ap-southeast-1',
    'aws-0-ap-northeast-1',
    'aws-0-ap-south-1',
    'aws-0-eu-central-1',
    'aws-0-ca-central-1',
    'aws-0-sa-east-1',
]

for r in regions:
    host = f'{r}.pooler.supabase.com'
    try:
        conn = psycopg2.connect(
            host=host, port=6543, dbname='postgres',
            user=f'postgres.crzymgnpzbdkpsqpaywu',
            password='rbWO2tBEgs7O87WI',
            sslmode='require', connect_timeout=5
        )
        print(f'SUCCESS: {host}')
        conn.close()
        break
    except psycopg2.OperationalError as e:
        err_msg = str(e)
        if 'Tenant' in err_msg:
            print(f'FAIL (tenant): {r}')
        elif 'timeout' in err_msg.lower() or 'could not' in err_msg.lower():
            print(f'FAIL (timeout/resolve): {r}')
        else:
            print(f'FAIL (other): {r} - {err_msg[:80]}')
    except Exception as e:
        print(f'FAIL (exception): {r} - {e}')
else:
    print('\nAll pooler regions failed. Trying direct connection...')
    # Try direct connection with IPv6
    try:
        conn = psycopg2.connect(
            host='db.crzymgnpzbdkpsqpaywu.supabase.co',
            port=5432, dbname='postgres',
            user='postgres',
            password='rbWO2tBEgs7O87WI',
            sslmode='require', connect_timeout=10
        )
        print('SUCCESS: Direct connection!')
        conn.close()
    except Exception as e:
        print(f'Direct connection failed: {e}')
