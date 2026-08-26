import sys
import os
import time
import json

# Ensure the app package can be found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.database.connection import SessionLocal
from app.models import ContractClause, ReviewStandardClause
from app.services.llm import get_embedding

try:
    from google.genai.errors import ClientError
except ImportError:
    class ClientError(Exception):
        pass

def generate_with_retry(text, max_retries=5):
    for attempt in range(max_retries):
        try:
            return get_embedding(text)
        except ClientError as e:
            if getattr(e, "code", None) == 429:
                print(f"Rate limit hit! Attempt {attempt+1}/{max_retries}.")
                delay = 20.0
                if hasattr(e, "message") and "RetryInfo" in str(e.message):
                    # attempt basic regex or string parsing if it's a string dict
                    pass
                print(f"Waiting for {delay} seconds before retrying...")
                time.sleep(delay)
            else:
                raise e
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                print(f"Rate limit hit (parsed from string)! Attempt {attempt+1}/{max_retries}.")
                delay = 20.0
                
                # simple extraction for `retryDelay': '19s'`
                if "'retryDelay': '" in err_str:
                    try:
                        start_idx = err_str.find("'retryDelay': '") + 15
                        end_idx = err_str.find("s'", start_idx)
                        if end_idx != -1:
                            delay = float(err_str[start_idx:end_idx]) + 2.0
                    except Exception:
                        pass

                print(f"Waiting for {delay} seconds before retrying...")
                time.sleep(delay)
            else:
                raise e
    raise Exception("Max retries exceeded for embedding generation.")

def main():
    print("Starting embedding generation...")
    db: Session = SessionLocal()
    
    successful_count = 0
    batch_size = 10
    
    try:
        # 1. Update ReviewStandardClause
        standards = db.query(ReviewStandardClause).filter(ReviewStandardClause.embedding == None).all()
        print(f"Found {len(standards)} ReviewStandardClauses missing embeddings.")
        for c in standards:
            print(f"Generating embedding for ReviewStandardClause {c.clause_number}...")
            c.embedding = generate_with_retry(c.text)
            successful_count += 1
            if successful_count % batch_size == 0:
                db.commit()
                print(f"Committed {successful_count} embeddings so far...")
        db.commit()
        
        # 2. Update ContractClause
        clauses = db.query(ContractClause).filter(ContractClause.embedding == None).all()
        print(f"Found {len(clauses)} ContractClauses missing embeddings.")
        for c in clauses:
            print(f"Generating embedding for ContractClause {c.clause_label}...")
            c.embedding = generate_with_retry(c.text)
            successful_count += 1
            if successful_count % batch_size == 0:
                db.commit()
                print(f"Committed {successful_count} embeddings so far...")
                
        db.commit()
        print(f"Embeddings generated and saved successfully! Total new: {successful_count}")
    except Exception as e:
        db.rollback()
        print(f"Generation aborted. Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
