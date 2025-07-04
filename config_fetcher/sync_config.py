import os
from pathlib import Path
from typing import Any, List

import yaml
from encryption_manager import EncryptionManager
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
CREDENTIALS_PATH = "credentials.json"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


class ConfigReader:
    def __init__(self):
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID")
        if not self.spreadsheet_id:
            raise ValueError("SPREADSHEET_ID environment variable is not set")

        self.credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
        self.service = build("sheets", "v4", credentials=self.credentials)
        self.sheet = self.service.spreadsheets()
        self.encryption_manager = EncryptionManager()

        self.configs_by_id = {}

    def read_sheet(self, range_name: str) -> List[List[str]]:
        result = self.sheet.values().get(spreadsheetId=self.spreadsheet_id, range=range_name).execute()
        return result.get("values", [])

    def process_configs(self):
        data = self.read_sheet("Configs!A:ZZ")
        headers = data[0]

        # Create a dict of configs indexed by Config Id
        for row in data[1:]:
            # Pad row with empty strings if shorter than headers
            row_data = row + [""] * (len(headers) - len(row))
            config = dict(zip(headers, row_data))
            config_id = config.pop("Config Id", None)
            if config_id:
                self.configs_by_id[config_id] = config

    def process_miners(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        data = self.read_sheet("Miners!A:ZZ")
        headers = data[0]
        active_hosts = {}
        all_hosts = {}

        # First, group by hostname
        for row in data[1:]:
            # Pad row with empty strings if shorter than headers
            row_data = row + [""] * (len(headers) - len(row))
            row_dict = dict(zip(headers, row_data))
            if not all([row_dict["Hotkey"], row_dict["Hostname"], row_dict["Branch"], row_dict["Config Id"]]):
                continue

            hostname = row_dict["Hostname"]
            if hostname not in all_hosts:
                all_hosts[hostname] = {"ansible_host": row_dict["IP"], "provider": row_dict["Provider"], "miners": []}

            if row_dict["Use"] == "TRUE" and hostname not in active_hosts:
                active_hosts[hostname] = {
                    "ansible_host": row_dict["IP"],
                    "provider": row_dict["Provider"],
                    "miners": [],
                }

            # Get config for this miner
            config_id = row_dict["Config Id"]
            config = self.configs_by_id.get(config_id, {})
            if not config:
                raise ValueError(
                    f"Config id: '{config_id}' for miner '{row_dict['Hotkey']}' could not be found in Configs table"
                )
            config["ID"] = config_id

            # Create miner entry
            miner = {
                "name": row_dict["Hotkey"],
                "port": row_dict["Port"],
                "branch": row_dict["Branch"],
                "config": config,
                "secrets": {
                    "openai_key": self.encryption_manager.encrypt(row_dict.get("OpenAI API key", "")),
                    "anthropic_key": self.encryption_manager.encrypt(row_dict.get("Anthropic API key", "")),
                    "google_key": self.encryption_manager.encrypt(row_dict.get("Google API key", "")),
                    "azure_key": self.encryption_manager.encrypt(row_dict.get("Azure API key", "")),
                    "perplexity_key": self.encryption_manager.encrypt(row_dict.get("Perplexity API key", "")),
                },
            }

            all_hosts[hostname]["miners"].append(miner)

            if row_dict["Use"] == "TRUE":
                active_hosts[hostname]["miners"].append(miner)

        return active_hosts, all_hosts

    def save_host_files(self, hosts: dict, dir_path: str) -> None:
        directory = Path(dir_path)
        directory.mkdir(exist_ok=True)

        created_files = set()
        for hostname, host_data in hosts.items():
            config_path = directory / f"{hostname}.yml"
            with open(config_path, "w") as f:
                yaml.dump(host_data, f, default_flow_style=False, sort_keys=False, Dumper=NoAliasDumper)
            created_files.add(config_path)

        for file_path in directory.glob("*.yml"):
            if file_path not in created_files:
                os.remove(file_path)


def fetch_and_save():
    reader = ConfigReader()

    # First process configs so we have them ready
    reader.process_configs()

    # Then process miners and create host_vars
    active_hosts, all_hosts = reader.process_miners()

    # Create files per host in specified directory
    reader.save_host_files(active_hosts, "host_vars")
    reader.save_host_files(all_hosts, "all_host_vars")


if __name__ == "__main__":
    fetch_and_save()
