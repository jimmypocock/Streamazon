.PHONY: help setup install run-web run-cli test clean docker-build docker-run format lint

# Default target
help:
	@echo "AWS Cost & Usage Monitor - Available Commands"
	@echo "============================================"
	@echo "  make setup        - Set up the development environment"
	@echo "  make install      - Install dependencies"
	@echo "  make run-web      - Run the Streamlit web dashboard"
	@echo "  make run-cli      - Show CLI help"
	@echo "  make test         - Run tests"
	@echo "  make format       - Format code with black"
	@echo "  make lint         - Run linting checks"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-run   - Run Docker container"
	@echo "  make clean        - Clean up temporary files"

# Setup development environment
setup:
	@echo "Setting up development environment..."
	@chmod +x scripts/setup.sh
	@./scripts/setup.sh

# Install dependencies
install:
	@echo "Installing dependencies..."
	@pip install --upgrade pip
	@pip install -r requirements.txt

# Run web dashboard
run-web:
	@echo "Starting Streamlit dashboard..."
	@streamlit run aws_monitor/web/streamlit_app.py

# Show CLI help
run-cli:
	@echo "AWS Cost Monitor CLI"
	@python -m aws_monitor.cli.cli --help

# Run tests
test:
	@echo "Running tests..."
	@pytest tests/ -v

# Run tests with coverage
test-coverage:
	@echo "Running tests with coverage..."
	@pytest tests/ --cov=aws_monitor --cov-report=html --cov-report=term

# Format code
format:
	@echo "Formatting code..."
	@black aws_monitor/ tests/
	@isort aws_monitor/ tests/

# Lint code
lint:
	@echo "Running linting checks..."
	@flake8 aws_monitor/ tests/
	@mypy aws_monitor/

# Build Docker image
docker-build:
	@echo "Building Docker image..."
	@docker build -t aws-cost-monitor:latest .

# Run Docker container
docker-run:
	@echo "Running Docker container..."
	@docker-compose up -d

# Stop Docker container
docker-stop:
	@echo "Stopping Docker container..."
	@docker-compose down

# View Docker logs
docker-logs:
	@docker-compose logs -f

# Clean up
clean:
	@echo "Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name "*.log" -delete
	@rm -rf .pytest_cache/
	@rm -rf htmlcov/
	@rm -rf .coverage
	@rm -rf dist/
	@rm -rf build/
	@rm -rf *.egg-info

# Deploy to ECS
deploy-ecs:
	@echo "Deploying to ECS..."
	@echo "Please follow the deployment instructions in the README"

# Check AWS credentials
check-aws:
	@echo "Checking AWS configuration..."
	@aws sts get-caller-identity
	@aws organizations describe-organization || echo "No Organizations access"

# Initialize Cost Explorer (one-time setup)
init-cost-explorer:
	@echo "Enabling Cost Explorer..."
	@echo "Note: Cost Explorer must be enabled in the AWS Console"
	@echo "Visit: https://console.aws.amazon.com/cost-management/home"

# Tail application logs
logs:
	@tail -f logs/*.log 2>/dev/null || echo "No log files found"

# Run security scan
security-scan:
	@echo "Running security scan..."
	@pip install bandit
	@bandit -r aws_monitor/ -f json -o security-report.json
	@echo "Security report generated: security-report.json"

# Generate documentation
docs:
	@echo "Generating documentation..."
	@pip install sphinx sphinx-rtd-theme
	@sphinx-quickstart -q -p "AWS Cost Monitor" -a "Your Name" -v "1.0" --ext-autodoc --ext-viewcode --makefile docs/
	@sphinx-apidoc -o docs/source aws_monitor/

# Show current costs (quick check)
quick-costs:
	@python -m aws_monitor.cli.cli costs --hours 24 --top 5