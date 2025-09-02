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
        Get all file hashes contributed by a specific wallet address.
        
        Args:
            wallet_address: The wallet address to check
            
        Returns:
            list: List of file hashes contributed by the address
        """
        try:
            contributor_info = self.contract.functions.contributorInfo(
                Web3.to_checksum_address(wallet_address)
            ).call()
            
            file_count = contributor_info[1]
            file_hashes = []
            
            for i in range(file_count):
                try:
                    file_hash = self.contract.functions.contributorFiles(
                        Web3.to_checksum_address(wallet_address), i
                    ).call()
                    if file_hash:
                        file_hashes.append(file_hash)
                except:
                    continue
                    
            return file_hashes
            
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
                    contributor_address = self.contract.functions.contributors(i).call()
                    if contributor_address:
                        contributors.append(contributor_address)
                except:
                    continue
                    
            return contributors
            
        except Exception as e:
            logging.error(f"Error getting all contributors: {str(e)}")
            return []
