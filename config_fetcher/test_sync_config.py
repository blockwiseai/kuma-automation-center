import pytest
from unittest.mock import Mock, patch

from sync_config import ConfigReader

@pytest.fixture
def mock_google_setup():
    """Setup mock for Google Sheets API"""
    with patch('sync_config.service_account.Credentials') as mock_creds, \
         patch('sync_config.build') as mock_build, \
         patch('sync_config.EncryptionManager'), \
         patch.dict('os.environ', {'SPREADSHEET_ID': 'dummy_id'}):

        # Create mock service
        mock_service = Mock()
        mock_sheet = Mock()
        mock_values = Mock()

        # Setup the chain of mocks
        mock_build.return_value = mock_service
        mock_service.spreadsheets.return_value = mock_sheet
        mock_sheet.values.return_value = mock_values
        mock_values.get.return_value.execute.return_value = {
            'values': [
                ['Header1', 'Header2'],
                ['Value1', 'Value2']
            ]
        }

        yield mock_sheet

def test_read_sheet(mock_google_setup):
    reader = ConfigReader()
    data = reader.read_sheet('Sheet1!A1:B2')

    assert len(data) == 2
    assert data[0] == ['Header1', 'Header2']
    assert data[1] == ['Value1', 'Value2']

class TestProcessConfig:

    def test_can_handle_missing_values(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                ['Config Id', 'PARAM_1', 'PARAM_2'],
                ['1', 'value11', 'value12'],
                ['2', 'value21', ''],
                ['3', '', 'value32'],
                ['4', '', ''],
                ['5'],
            ]
        }

        reader = ConfigReader()
        reader.process_configs()

        parsed_configs = reader.configs_by_id

        assert len(parsed_configs) == 5
        assert parsed_configs['1'] == {"PARAM_1": "value11", "PARAM_2": "value12"}
        assert parsed_configs['2'] == {"PARAM_1": "value21", "PARAM_2": ""}
        assert parsed_configs['3'] == {"PARAM_1": "", "PARAM_2": "value32"}
        assert parsed_configs['4'] == {"PARAM_1": "", "PARAM_2": ""}
        assert parsed_configs['5'] == {"PARAM_1": "", "PARAM_2": ""}

    def test_can_handle_superflous_values(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                ['Config Id', 'PARAM_1', 'PARAM_2'],
                ['1', 'value11', 'value12', 'value13'],
                ['2', 'value21', 'value22', ''],
            ]
        }

        reader = ConfigReader()
        reader.process_configs()

        parsed_configs = reader.configs_by_id

        assert len(parsed_configs) == 2
        assert parsed_configs['1'] == {"PARAM_1": "value11", "PARAM_2": "value12"}
        assert parsed_configs['2'] == {"PARAM_1": "value21", "PARAM_2": "value22"}

    def test_ignore_rows_with_missing_id(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                ['Config Id', 'PARAM_1', 'PARAM_2'],
                ['', 'value11', 'value12', 'value13'],
                [],
            ]
        }

        reader = ConfigReader()
        reader.process_configs()

        parsed_configs = reader.configs_by_id

        assert len(parsed_configs) == 0, "No empty rows should be parsed"

class TestProcessMiners:
    header = [
        'Hostname', 'Provider', 'IP', 'Port', 'Hotkey', 'Branch', 'Config Id', 'Use',
        'OpenAI API key', 'Anthropic API key', 'Google API key', 'Azure API key', 'Perplexity API key'
    ]

    def test_single_host_holds_multiple_miners(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                self.header,
                ['s6_6a1', 'AWS', '192.168.1.101', '8001', '6a01', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
                ['s6_6a1', 'AWS', '192.168.1.101', '8002', '6a02', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
                ['s6_6b2', 'AWS', '192.168.1.108', '8000', '6b01', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
            ]
        }

        reader = ConfigReader()
        reader.configs_by_id = {"1": {"param": "value"}}
        active_hosts, all_hosts = reader.process_miners()

        assert len(active_hosts) == 2
        assert set(active_hosts.keys()) == {'s6_6a1', 's6_6b2'}
        assert len(active_hosts['s6_6a1']['miners']) == 2

    def test_all_input_fields_present_in_output(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                self.header,
                ['s6_6a1', 'AWS', '192.168.1.101', '8001', '6a01', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
            ]
        }

        reader = ConfigReader()
        reader.configs_by_id = {"1": {"param": "value"}}
        active_hosts, all_hosts = reader.process_miners()

        host_data = all_hosts['s6_6a1']
        assert host_data['ansible_host'] == '192.168.1.101'
        assert host_data['provider'] == 'AWS'
        miner = host_data['miners'][0]
        assert miner['name'] == '6a01'
        assert miner['port'] == '8001'
        assert miner['branch'] == 'main'
        assert miner['config'] == {"param": "value"}
        # Now secrets should contain five keys
        assert len(miner['secrets']) == 5

    def test_ignoring_rows_with_no_hotkey(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                self.header,
                ['s6_6a1', 'AWS', '192.168.1.101', '8001', '', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
                ['s6_6a2', 'AWS', '192.168.2.101', '8003', '6a02', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
                ['s6_6a2', 'AWS', '192.168.3.101', '8004', '', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
            ]
        }

        reader = ConfigReader()
        reader.configs_by_id = {"1": {"param": "value"}}
        active_hosts, all_hosts = reader.process_miners()

        assert len(all_hosts) == 1
        assert len(all_hosts['s6_6a2']['miners']) == 1
        assert all_hosts['s6_6a2']['miners'][0]['name'] == '6a02'

    def test_config_is_loaded_by_id(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                self.header,
                ['s6_6a1', 'AWS', '192.168.1.101', '8001', '6a01', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
                ['s6_6b2', 'AWS', '192.168.2.101', '8003', '6b01', 'main', '2', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
                ['s6_6b2', 'AWS', '192.168.2.101', '8004', '6b02', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
            ]
        }

        reader = ConfigReader()
        reader.configs_by_id = {"1": {"param": "value1"}, "2": {"param": "value2"}}
        active_hosts, all_hosts = reader.process_miners()

        miners_s6_6a1 = all_hosts['s6_6a1']['miners']
        miners_s6_6b2 = all_hosts['s6_6b2']['miners']
        assert miners_s6_6a1[0]['config'] == {"param": "value1"}
        assert miners_s6_6b2[0]['config'] == {"param": "value2"}
        assert miners_s6_6b2[1]['config'] == {"param": "value1"}

    def test_invalid_config_throws(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                self.header,
                ['s6_6a1', 'AWS', '192.168.1.101', '8001', '6a01', 'main', '3', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
            ]
        }

        reader = ConfigReader()
        reader.configs_by_id = {"1": {"param": "value1"}, "2": {"param": "value2"}}

        with pytest.raises(ValueError) as excinfo:
            reader.process_miners()
        assert str(excinfo.value) == "Config id: '3' for miner '6a01' could not be found in Configs table"

    def test_missing(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                self.header,
                ['', 'AWS', '192.168.1.101', '8001', '6a01', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
            ]
        }

        reader = ConfigReader()
        reader.configs_by_id = {"1": {"param": "value1"}, "2": {"param": "value2"}}
        active_hosts, all_hosts = reader.process_miners()
        assert active_hosts == {}
        assert all_hosts == {}

    def test_active_and_all_counts_differ(self, mock_google_setup):
        mock_google_setup.values().get().execute.return_value = {
            'values': [
                self.header,
                ['s6_6a1', 'AWS', '192.168.1.101', '8001', '6a01', 'main', '1', 'TRUE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key'],
                ['s6_6a2', 'AWS', '192.168.2.101', '8002', '6a02', 'main', '1', 'FALSE',
                 'openai_key', 'anthropic_key', 'google_key', 'azure_key', 'perplexity_key']
            ]
        }

        reader = ConfigReader()
        reader.configs_by_id = {"1": {"param": "value"}}
        active_hosts, all_hosts = reader.process_miners()

        assert len(all_hosts) == 2
        assert len(active_hosts) == 1
        assert len(all_hosts) != len(active_hosts)
