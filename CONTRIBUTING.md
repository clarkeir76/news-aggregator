# CONTRIBUTING.md

## Development Setup

### Local Development Environment

```bash
# Clone the repository
git clone <repository>
cd news-aggregator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
make dev-install

# Copy environment file
cp .env.example .env

# Edit .env with your local configuration
```

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest tests/test_models.py -v

# Run with debug output
pytest tests/ -v -s
```

### Code Quality

```bash
# Format code
make format

# Check formatting
black --check app/ tests/

# Lint code
make lint

# Type checking
mypy app/src/ --ignore-missing-imports
```

## Development Workflow

1. **Create feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes**
   - Write tests first (TDD)
   - Implement feature
   - Update documentation

3. **Run tests locally**
   ```bash
   make test-cov
   ```

4. **Format and lint**
   ```bash
   make format
   make lint
   ```

5. **Commit changes**
   ```bash
   git add .
   git commit -m "feat: description of changes"
   ```

6. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Address review comments**

8. **Merge to main**

## Pull Request Guidelines

- Write clear PR title and description
- Reference any related issues
- Ensure all tests pass
- Code coverage should not decrease
- Update README if adding new features
- Update CHANGELOG

## Code Style

- Follow PEP 8
- Use type hints where possible
- Write docstrings for all functions
- Keep functions small and focused
- Use descriptive variable names

## Commit Messages

Follow conventional commits:

```
feat: add new feature
fix: fix a bug
docs: update documentation
test: add tests
refactor: refactor code
perf: improve performance
chore: maintenance tasks
```

## Testing

- Write tests for new code
- Maintain >80% code coverage
- Test edge cases
- Mock external APIs
- Use fixtures for common setup

## Documentation

Update relevant documentation when:
- Adding new features
- Changing API/configuration
- Fixing bugs that are non-obvious
- Updating dependencies

## Questions?

- Open an issue for questions
- Check existing issues first
- Use discussions for broader topics

Thank you for contributing!
