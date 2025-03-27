import jwt
import requests
from jwt import PyJWTError

CLERK_JWKS_URL = "https://rich-werewolf-5.clerk.accounts.dev/.well-known/jwks.json"

def get_clerk_public_key(kid):
    """
    Fetch Clerk's public keys and return the key matching the given 'kid'.
    """
    try:
        response = requests.get(CLERK_JWKS_URL)
        response.raise_for_status()
        jwks = response.json()
        for key in jwks["keys"]:
            if key["kid"] == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
    except requests.RequestException as e:
        raise Exception(f"Failed to fetch Clerk JWKS: {str(e)}")
    return None

def verify_clerk_jwt(token):
    """
    Verify a JWT token issued by Clerk.
    """
    try:
        # Decode the token header to get the 'kid'
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise Exception("Token header does not contain 'kid'")

        # Get the public key for the given 'kid'
        public_key = get_clerk_public_key(kid)
        if not public_key:
            raise Exception("Public key not found for 'kid'")

        # Verify the token
        decoded_token = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer="https://rich-werewolf-5.clerk.accounts.dev"  # Replace with your Clerk issuer
        )
        return decoded_token
    except PyJWTError as e:
        raise Exception(f"JWT verification failed: {str(e)}")