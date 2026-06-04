import sys
import pytest
from app.security.sandbox.error_detector import (
    SandboxErrorDetector,
    SandboxErrorInfo,
    SandboxErrorType,
)


@pytest.fixture
def detector():
    return SandboxErrorDetector()


class TestSeatbeltNetworkDetection:
    def test_seatbelt_deny_network_high_confidence(self, detector):
        stderr = 'sandbox-exec[123]: deny network-out (Host: pypi.org)'
        result = detector.detect(returncode=1, stderr=stderr, platform="darwin")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
        assert result.confidence == "high"
        assert result.denied_paths == []

    def test_seatbelt_deny_network_multiple_patterns(self, detector):
        stderr = 'deny network* (Host: registry.npmjs.org)'
        result = detector.detect(returncode=1, stderr=stderr, platform="darwin")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
        assert result.confidence == "high"


class TestSeatbeltPathDetection:
    def test_seatbelt_deny_file_read(self, detector):
        stderr = 'deny file-read* (subpath "/Users/test/secrets")'
        result = detector.detect(returncode=1, stderr=stderr, platform="darwin")
        assert result is not None
        assert result.error_type == SandboxErrorType.PATH_DENIED
        assert result.confidence == "high"
        assert "/Users/test/secrets" in result.denied_paths

    def test_seatbelt_deny_file_write(self, detector):
        stderr = 'deny file-write* (subpath "/tmp/cache")'
        result = detector.detect(returncode=1, stderr=stderr, platform="darwin")
        assert result is not None
        assert result.error_type == SandboxErrorType.PATH_DENIED
        assert "/tmp/cache" in result.denied_paths

    def test_seatbelt_deny_multiple_paths(self, detector):
        stderr = (
            'deny file-read* (subpath "/etc/ssl")\n'
            'deny file-write* (subpath "/var/log")'
        )
        result = detector.detect(returncode=1, stderr=stderr, platform="darwin")
        assert result is not None
        assert result.error_type == SandboxErrorType.PATH_DENIED
        assert "/etc/ssl" in result.denied_paths
        assert "/var/log" in result.denied_paths


class TestBwrapNetworkDetection:
    def test_bwrap_network_unreachable(self, detector):
        stderr = 'pip is configured with locations that require TLS/HTTPS\nNetwork is unreachable'
        result = detector.detect(returncode=1, stderr=stderr, platform="linux")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
        assert result.confidence == "medium"

    def test_bwrap_could_not_resolve(self, detector):
        stderr = 'Could not resolve host: pypi.org'
        result = detector.detect(returncode=1, stderr=stderr, platform="linux")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
        assert result.confidence == "medium"


class TestNoDetection:
    def test_exit_code_zero_no_detection(self, detector):
        result = detector.detect(returncode=0, stderr="some output", platform="darwin")
        assert result is None

    def test_unknown_stderr_no_detection(self, detector):
        result = detector.detect(returncode=1, stderr="SyntaxError: invalid syntax", platform="darwin")
        assert result is None

    def test_empty_stderr_nonzero_exit(self, detector):
        result = detector.detect(returncode=1, stderr="", platform="darwin")
        assert result is None


class TestRegistryAuxiliary:
    def test_network_error_with_often_needs_network(self, detector):
        from app.security.command_effect_registry import CommandEffectRegistry
        registry = CommandEffectRegistry()
        result = detector.detect(
            returncode=1,
            stderr="Connection refused",
            command_argv=["pip", "install", "requests"],
            registry=registry,
            platform="darwin",
        )
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
        assert result.confidence == "medium"

    def test_network_error_without_registry_no_match(self, detector):
        result = detector.detect(
            returncode=1,
            stderr="Connection refused",
            command_argv=["somecmd", "arg"],
            platform="darwin",
        )
        assert result is None


class TestPythonNetworkErrors:
    def test_socket_gaierror_errno8(self, detector):
        stderr = 'socket.gaierror: [Errno 8] nodename nor servname provided, or not known'
        result = detector.detect(returncode=1, stderr=stderr, platform="darwin")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
        assert result.confidence == "high"

    def test_urlopen_error_errno8(self, detector):
        stderr = 'urllib.error.URLError: <urlopen error [Errno 8] nodename nor servname provided>'
        result = detector.detect(returncode=1, stderr=stderr, platform="darwin")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
        assert result.confidence == "high"

    def test_requests_connection_error(self, detector):
        stderr = 'requests.exceptions.ConnectionError: HTTPSConnectionPool(host=\'pypi.org\'): Max retries exceeded'
        result = detector.detect(returncode=1, stderr=stderr, platform="darwin")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
        assert result.confidence == "high"

    def test_new_connection_error(self, detector):
        stderr = 'urllib3.exceptions.NewConnectionError: Failed to establish a new connection'
        result = detector.detect(returncode=1, stderr=stderr, platform="darwin")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
        assert result.confidence == "high"

    def test_getaddrinfo_failed(self, detector):
        stderr = 'socket.gaierror: getaddrinfo failed'
        result = detector.detect(returncode=1, stderr=stderr, platform="linux")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED

    def test_python_network_error_on_linux(self, detector):
        stderr = 'requests.exceptions.ConnectionError: Failed to establish a new connection'
        result = detector.detect(returncode=1, stderr=stderr, platform="linux")
        assert result is not None
        assert result.error_type == SandboxErrorType.NETWORK_DENIED
