# Kuma Center

This project automates the monitoring using Up-time Kuma and adds restarting of miners. It consists of four main components:

1. **`kuma`**: Up-time Kuma
2. **`config_fetcher`**: Loads miner configuration data from a Google Spreadsheet.
3. **`kuma_updater`**: Moves miners between `active` and `inactive` groups based on spreadsheet data checked against metagraph, it also verifies miner parameters against metagraph, and sends restart signals to the `miner_restarter` service.
4. **`miner_restarter`**: Uses Ansible to restart miner services that fall outside the expected parameters.

## Base necessities

Before spinning up the project, ensure you:

- Fill out the `.env` file with your environment-specific variables.
- Create a Google Service Account with access to the subnet configuration spreadsheet, then place its `credentials.json` in `config_fetcher/`.


