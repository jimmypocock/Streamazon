# Contributing to AWS Cost & Usage Monitor

Thank you for your interest in contributing to AWS Cost & Usage Monitor! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to abide by our code of conduct:

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Respect differing viewpoints and experiences

## How to Contribute

### Reporting Issues

1. Check if the issue already exists
2. Create a new issue with a clear title and description
3. Include:
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Environment details (OS, Python version, AWS region)
   - Error messages or logs

### Suggesting Features

1. Check if the feature has already been requested
2. Create a new issue with the "enhancement" label
3. Describe:
   - The problem you're trying to solve
   - Your proposed solution
   - Alternative solutions you've considered

### Submitting Pull Requests

1. Fork the repository
2. Create a new branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Write or update tests
5. Update documentation
6. Commit using clear messages: `git commit -m "Add feature: description"`
7. Push to your fork: `git push origin feature/your-feature-name`
8. Create a pull request

## Development Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/aws-cost-usage-monitor.git
   cd aws-cost-usage-monitor
   ```

2. Create a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # Development dependencies
   ```

4. Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Code Style

- Follow PEP 8
- Use type hints where appropriate
- Maximum line length: 100 characters
- Use descriptive variable names
- Add docstrings to all functions and classes

### Running Code Quality Checks

```bash
# Format code
black aws_monitor/

# Check style
flake8 aws_monitor/

# Sort imports
isort aws_monitor/

# Type checking
mypy aws_monitor/
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=aws_monitor --cov-report=html

# Run specific test file
pytest tests/test_cost_analyzer.py

# Run with verbose output
pytest -v
```

### Writing Tests

- Place tests in the `tests/` directory
- Mirror the source code structure
- Use descriptive test names
- Test both success and failure cases
- Mock AWS API calls

Example test:

```python
def test_cost_breakdown_calculation():
    """Test that cost breakdown correctly calculates percentages."""
    # Arrange
    analyzer = CostAnalyzer(mock_client)

    # Act
    result = analyzer.get_cost_breakdown(hours=24)

    # Assert
    assert result['total_cost'] > 0
    assert sum(item['percentage'] for item in result['breakdown']) == 100
```

## Documentation

- Update README.md for user-facing changes
- Add docstrings to new functions and classes
- Update configuration examples if needed
- Include examples in docstrings

## AWS API Considerations

- Minimize API calls to avoid rate limits
- Cache responses where appropriate
- Handle pagination properly
- Always handle errors gracefully
- Test with minimal AWS permissions

## Security

- Never commit AWS credentials
- Use IAM roles instead of access keys
- Follow the principle of least privilege
- Sanitize any user input
- Don't log sensitive information

## Pull Request Process

1. Ensure all tests pass
2. Update documentation
3. Add your changes to CHANGELOG.md
4. Request review from maintainers
5. Address review feedback
6. Squash commits if requested

## Release Process

1. Update version in `aws_monitor/__init__.py`
2. Update CHANGELOG.md
3. Create a new tag: `git tag v1.0.0`
4. Push tag: `git push origin v1.0.0`
5. Create GitHub release with notes

## Getting Help

- Check the documentation
- Search existing issues
- Ask in discussions
- Contact maintainers

## Recognition

Contributors will be recognized in:

- README.md contributors section
- Release notes
- Project documentation

Thank you for contributing to AWS Cost & Usage Monitor!
