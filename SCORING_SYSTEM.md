# V! DataDAO Scoring System

## What It Scores

The system evaluates **Instagram** and **Google profile** data contributions with scores from 0 to 1.

## How It Scores

### 4 Main Categories:

1. **Quality (35-40%)**

   - Schema validation
   - Data completeness
   - Profile fields filled
   - Activity data present

2. **Authenticity (30-35%)**

   - Google OAuth verification
   - Phone/email confirmation
   - Data consistency checks
   - Source verification

3. **Uniqueness (20%)**

   - Account age (1+ years = max points)
   - Posts count (100+ = max points)
   - Likes/comments activity
   - Network size (followers + following)

4. **Ownership (10%)**
   - Wallet address verification
   - Either 1.0 or 0.0

## Formula

**Instagram:** `Score = Quality×0.35 + Authenticity×0.35 + Uniqueness×0.20 + Ownership×0.10`

**Google:** `Score = Quality×0.40 + Authenticity×0.30 + Uniqueness×0.20 + Ownership×0.10`

## Validation

- JSON schema check
- Google OAuth verification
- Blockchain duplicate prevention
- Profile matching

---

_Created by: altay_
