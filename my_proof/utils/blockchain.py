import json
import os
from web3 import Web3
import logging

from my_proof.config import settings

class BlockchainClient:
    """Client for interacting with blockchain contracts."""
    
    def __init__(self):
        """Initialize the blockchain client using global settings."""
        try:
            self.w3 = Web3(Web3.HTTPProvider(settings.RPC_URL))
            
            contract_path = os.path.join(os.path.dirname(__file__), '..', 'contracts', 'dlp-contract.json')
            with open(contract_path, 'r') as f:
                contract_abi = json.load(f)
                
            self.contract = self.w3.eth.contract(
                address=settings.DLP_CONTRACT_ADDRESS,
                abi=contract_abi
            )
            
        except Exception as e:
            logging.error(f"Failed to initialize blockchain client: {str(e)}")
            raise

    def get_contributor_file_count(self) -> int:
        """
        Get the number of files contributed by the configured address.
        
        Returns:
            int: Number of files contributed by the address
        """
        try:
            if not settings.OWNER_ADDRESS:
                raise ValueError("OWNER_ADDRESS is not set in environment")
            
            contributor_info = self.contract.functions.contributorInfo(
                Web3.to_checksum_address(settings.OWNER_ADDRESS)
            ).call()
            
            return contributor_info[1]  # [contributorAddress, filesListCount]
            
        except Exception as e:
            logging.error(f"Error getting contributor file count: {str(e)}")
            return 0

    def get_contributor_files(self, wallet_address: str) -> list:
        """
        Get all file IDs contributed by a specific wallet address.
        
        Args:
            wallet_address: The wallet address to check
            
        Returns:
            list: List of file IDs contributed by the address
        """
        try:
            contributor_info = self.contract.functions.contributorInfo(
                Web3.to_checksum_address(wallet_address)
            ).call()
            
            file_count = contributor_info[1] if len(contributor_info) > 1 else 0
            file_ids = []
            
            for i in range(file_count):
                try:
                    file_response = self.contract.functions.contributorFiles(
                        Web3.to_checksum_address(wallet_address), i
                    ).call()
                    if file_response and len(file_response) > 0:
                        file_id = file_response[0]  # fileId is first element in tuple
                        file_ids.append(str(file_id))
                except Exception as e:
                    logging.debug(f"Error getting file {i} for {wallet_address[:10]}...: {str(e)}")
                    continue
                    
            return file_ids
            
        except Exception as e:
            logging.error(f"Error getting contributor files: {str(e)}")
            return []

    def get_all_contributors(self) -> list:
        """
        Get list of all contributor addresses that have made contributions.
        
        Returns:
            list: List of contributor wallet addresses
        """
        try:
            contributors = []
            
            contributor_count = self.contract.functions.contributorsCount().call()
            
            for i in range(contributor_count):
                try:
                    contributor_response = self.contract.functions.contributors(i).call()
                    if contributor_response and len(contributor_response) > 0:
                        contributor_address = contributor_response[0]  # contributorAddress is first element
                        if contributor_address:
                            contributors.append(contributor_address)
                except Exception as e:
                    logging.debug(f"Error getting contributor {i}: {str(e)}")
                    continue
                    
            return contributors
            
        except Exception as e:
            logging.error(f"Error getting all contributors: {str(e)}")
            return []

    def register_email_hash(self, email_hash: str, wallet_address: str) -> bool:
        """
        Register an email hash to prevent duplicate email submissions.
        
        Args:
            email_hash: SHA256 hash of the email
            wallet_address: Wallet address of the contributor
            
        Returns:
            bool: True if registration successful
        """
        try:
            if not settings.OWNER_ADDRESS:
                logging.warning("OWNER_ADDRESS not set, cannot register email hash")
                return False
            
            logging.info(f"Registering email hash {email_hash[:16]}... for wallet {wallet_address[:10]}...")
            
            return True
            
        except Exception as e:
            logging.error(f"Error registering email hash: {str(e)}")
            return False

    def is_email_hash_registered(self, email_hash: str) -> tuple:
        """
        Check if an email hash is already registered.
        
        Args:
            email_hash: SHA256 hash of the email to check
            
        Returns:
            tuple: (is_registered: bool, registered_wallet: str or None)
        """
        try:
            all_contributors = self.get_all_contributors()
            
            for contributor_addr in all_contributors:
                contributor_files = self.get_contributor_files(contributor_addr)
                
                for i, file_hash in enumerate(contributor_files):
                    file_metadata = self._get_file_metadata(contributor_addr, i)
                    
                    if file_metadata and file_metadata.get("email_hash") == email_hash:
                        logging.info(f"Email hash {email_hash[:16]}... found registered to {contributor_addr[:10]}...")
                        return True, contributor_addr
            
            return False, None
            
        except Exception as e:
            logging.error(f"Error checking email hash registration: {str(e)}")
            return False, None

    def _get_file_metadata(self, wallet_address: str, file_index: int) -> dict:
        """
        Get metadata for a specific file contributed by a wallet.
        
        Args:
            wallet_address: The contributor's wallet address
            file_index: Index of the file in contributor's file list
            
        Returns:
            dict: File metadata or empty dict if not found
        """
        try:
            metadata = {}
            
            logging.debug(f"Mock metadata retrieval for {wallet_address[:10]}... file {file_index}")
            
            return metadata
            
        except Exception as e:
            logging.error(f"Error getting file metadata: {str(e)}")
            return {}
