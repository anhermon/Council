import pytest
from council.tools.scribe import validate_url, validate_topic

class TestValidateUrl:
    def test_valid_url(self):
        """Test valid URLs."""
        validate_url("https://example.com/docs")
        validate_url("http://api.service.com/v1/spec")
        validate_url("https://github.com/owner/repo")

    def test_invalid_scheme(self):
        """Test invalid URL schemes."""
        with pytest.raises(ValueError, match="Only http and https schemes are allowed"):
            validate_url("ftp://example.com")
        
        with pytest.raises(ValueError, match="Only http and https schemes are allowed"):
            validate_url("file:///etc/passwd")

    def test_localhost_blocked(self):
        """Test localhost blocking."""
        with pytest.raises(ValueError, match="Access to localhost is not allowed"):
            validate_url("http://localhost:8000")
            
        with pytest.raises(ValueError, match="Access to localhost is not allowed"):
            validate_url("http://127.0.0.1")
            
        with pytest.raises(ValueError, match="Access to localhost is not allowed"):
            validate_url("http://[::1]")

    def test_private_ip_blocked(self):
        """Test private IP blocking."""
        with pytest.raises(ValueError, match="Access to private IP .* is not allowed"):
            validate_url("http://192.168.1.1")
            
        with pytest.raises(ValueError, match="Access to private IP .* is not allowed"):
            validate_url("http://10.0.0.1")

    def test_internal_domain_blocked(self):
        """Test internal domain blocking."""
        with pytest.raises(ValueError, match="Access to internal domain .* is not allowed"):
            validate_url("http://server.local")
            
        with pytest.raises(ValueError, match="Access to internal domain .* is not allowed"):
            validate_url("http://corp.internal")

class TestValidateTopic:
    def test_valid_topic(self):
        """Test valid topics."""
        assert validate_topic("python_best_practices") == "python_best_practices"
        assert validate_topic("react-patterns") == "react-patterns"
        assert validate_topic("v1_api_docs") == "v1_api_docs"

    def test_invalid_characters(self):
        """Test invalid characters in topic."""
        with pytest.raises(ValueError, match="Topic name must contain only alphanumeric"):
            validate_topic("my topic")
            
        with pytest.raises(ValueError, match="Topic name must contain only alphanumeric"):
            validate_topic("topic!")

    def test_path_traversal(self):
        """Test path traversal in topic."""
        with pytest.raises(ValueError, match="Topic name cannot contain path traversal"):
            validate_topic("../secret")
            
        with pytest.raises(ValueError, match="Topic name cannot contain path traversal"):
            validate_topic("dir/topic")
