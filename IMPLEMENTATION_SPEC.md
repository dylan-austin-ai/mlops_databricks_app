# Databricks MLOps App: Complete Implementation Specification

## Executive Summary

This document provides all technical details needed for Claude Code (or development team) to build the Databricks MLOps App from scratch. It includes architecture decisions, detailed feature specs, API interfaces, testing strategy, and deployment procedures.

**Target**: Production-ready, open-source app by [timeline].

---

## Table of Contents

1. [Technology Stack & Decisions](#technology-stack--decisions)
2. [Architecture & Design Patterns](#architecture--design-patterns)
3. [Feature Implementation Specifications](#feature-implementation-specifications)
4. [API Specifications](#api-specifications)
5. [Frontend Implementation Details](#frontend-implementation-details)
6. [Backend Implementation Details](#backend-implementation-details)
7. [Integration Points](#integration-points)
8. [Testing Strategy](#testing-strategy)
9. [Deployment & Operations](#deployment--operations)
10. [File Structure & Codebase Organization](#file-structure--codebase-organization)
11. [Dependencies & Prerequisites](#dependencies--prerequisites)
12. [Implementation Timeline & Milestones](#implementation-timeline--milestones)
13. [Known Risks & Mitigation](#known-risks--mitigation)

---

## Technology Stack & Decisions

### Frontend

**Framework**: Streamlit
- ✅ Rationale: Simple Python-based UI, no JavaScript needed, fast iteration
- ✅ Handles tables, forms, state management natively
- ✅ Can display Plotly charts, markdown, custom components
- ✅ Easy deployment to Databricks Workspace
- ✅ Data scientist-friendly (they already know Python)

**Alternative Considered**: React
- ❌ Rejected: Requires JavaScript expertise, more complex state management, harder for data scientists to customize

**Charting Library**: Plotly
- ✅ Time series, distributions, heatmaps all supported
- ✅ Interactive (hover, zoom, pan)
- ✅ Integrates seamlessly with Streamlit

**State Management**: Streamlit Session State + UC Tables
- ✅ Session state for UI-level state (current step in interview, selected tab, etc.)
- ✅ UC tables for persistent state (projects, configs, approvals)
- ✅ No need for Redis/external state store
- ✅ Audit trail automatically built-in (UC is append-only)

### Backend

**Language**: Python 3.10+
- ✅ Matches data scientist skill set
- ✅ Databricks SDKs are Python-first

**API Framework**: Databricks Model Serving (built-in)
- ✅ No separate API server needed
- ✅ MLflow models automatically serve REST endpoints
- ✅ Auto-scaling, monitoring, logging built-in
- ✅ All inference APIs are Databricks Model Serving calls

**Orchestration**: Databricks Workflows (formerly Jobs)
- ✅ Native Databricks integration
- ✅ No need for external orchestrators (Airflow, etc.)
- ✅ Built-in error handling, retries, notifications
- ✅ Cost tracking integrated

**Data Store**: Unity Catalog + Delta Lake
- ✅ All state in UC tables
- ✅ Immutable, auditable, compliant
- ✅ Time-travel for reproducibility
- ✅ Fine-grained access control

### Development Tools

**Version Control**: Git + GitHub
- ✅ Standard for open source
- ✅ GitHub Actions for CI/CD
- ✅ Repo auto-generation templates

**Package Management**: pip + requirements.txt
- ✅ Dependencies pinned to versions
- ✅ Generated per project

**Testing**: pytest
- ✅ Standard Python testing framework
- ✅ Easy to integrate with CI/CD
- ✅ Fixtures and parametrization support

**Linting/Formatting**:
- ✅ black (code formatting)
- ✅ isort (import sorting)
- ✅ pylint (linting, score >= 8.0)
- ✅ mypy (type checking, 100% coverage)
- ✅ pydocstyle (docstrings)

**Security**: pip-audit
- ✅ Dependency vulnerability scanning
- ✅ Fails on critical vulnerabilities
- ✅ Weekly rescans in CI/CD

---

## Architecture & Design Patterns

### 1. Interview System

**Pattern**: Multi-step wizard with collapsible sections

```python
class InterviewStep:
    """Base class for interview steps"""
    step_number: int
    step_name: str
    questions: List[Question]
    has_defaults: bool  # All fields have defaults?
    
    def validate(self) -> Tuple[bool, str]:
        """Validate step answers"""
        pass
    
    def get_defaults(self) -> Dict:
        """Return default answers for this step"""
        pass
    
    def render_ui(self, state: SessionState) -> None:
        """Render Streamlit UI for this step"""
        pass

class Question:
    """Individual question in interview"""
    field_name: str
    question_text: str
    question_type: str  # text, select, multiselect, int, float, boolean, cron, path, email, column
    required: bool
    default_value: Any
    options: List[str]  # For select/multiselect
    help_text: str
    validation_rules: List[Callable]
    
    def render(self) -> Any:
        """Render question in Streamlit"""
        pass
```

**Implementation**:
- Interview is 7 steps (see wireframes)
- Step 1: What would you like to do? (Use case selection - multi-select)
- Step 2: Model basics (name, problem, success metric, owner, team)
- Step 3: Data specifications (location, target, features, PII)
- Step 4: Governance (fairness, data quality)
- Step 5: Deployment (retraining, rollback, canary)
- Step 6: Monitoring (alerts, thresholds)
- Step 7: Governance gates (approvals, testing)
- Step 8: Review & create

Each step should:
1. Start collapsed if all fields have valid defaults
2. Show "Using defaults unless overridden" if collapsed
3. Expand on click
4. Show "✓ This matches org standard" vs "⚠️ Different from org standard"
5. Validate before proceeding to next step

### 2. Project Configuration System

**Pattern**: Versioned JSON stored in UC tables

```python
class ProjectConfig:
    """Project configuration (versioned)"""
    project_id: str
    config_version: int
    created_timestamp: datetime
    created_by: str
    
    # Immutable interview snapshot
    interview_responses: Dict[str, Any]
    
    def get_approval_gates(self) -> List[str]:
        """Which gates required for this project?"""
        pass
    
    def get_monitoring_config(self) -> Dict:
        """Monitoring configuration"""
        pass
    
    def commit(self, reason: str, user_email: str) -> str:
        """Create new version in UC"""
        pass
```

**Implementation**:
- Store in `mlops.project_configurations` table
- On any config change: create new version, don't update existing
- All changes tracked in audit logs
- Support rollback to previous config version

### 3. Data Contract System

**Pattern**: JSON schema with UI editor + Git versioning

```python
class DataContract:
    """Contract for data input/output"""
    contract_id: str
    project_id: str
    contract_type: str  # input_data, output_data, feature_table, staging_table
    
    table_name: str
    uc_path: str
    
    columns: List[ContractColumn]
    quality_rules: Dict[str, Any]
    
    def validate_data(self, df: DataFrame) -> ValidationResult:
        """Check if data matches contract"""
        pass
    
    def to_json(self) -> str:
        """Export as JSON schema"""
        pass
    
    def from_table(self, table_path: str) -> None:
        """Infer schema from existing table"""
        pass

class ContractColumn:
    """Individual column in contract"""
    name: str
    data_type: str
    nullable: bool
    unique: bool
    description: str
    pii_level: str  # none, low, medium, high
    classification: str
    quality_rules: Dict[str, Any]
    fairness_attribute: bool
    required_for_quality: bool
    monitor_for_drift: bool
```

**Implementation**:
1. **Create from scratch**: User enters column names and types manually
2. **Import CSV**: Parse CSV, auto-detect types, DS confirms
3. **From existing table**: 
   - Query table schema
   - Sample data (1000 rows)
   - Call LLM cluster to suggest: PII level, classification, descriptions
   - DS reviews and approves
4. **UI Editor**: 
   - Editable table showing all columns
   - Click row to expand details
   - Add/remove/edit columns
5. **Versioning**:
   - Each contract has version number
   - Changes require commit (in app)
   - Store version history in `mlops.data_contract_versions`
   - Git commit hash captured
6. **JSON Export**:
   - Save to `contracts/input_data.json` in repo
   - Save to `contracts/output_data.json`
   - Other tables as needed

### 4. Auto-Generation System

**Pattern**: Template rendering + code generation

```python
class ProjectGenerator:
    """Generate all artifacts for new project"""
    
    def __init__(self, project_config: ProjectConfig):
        self.config = project_config
    
    def generate_github_repo(self) -> str:
        """Create GitHub repo with templates"""
        pass
    
    def generate_skeleton_code(self) -> Dict[str, str]:
        """Generate train.py, evaluate.py, etc."""
        pass
    
    def generate_ci_cd_pipelines(self) -> Dict[str, str]:
        """Generate .github/workflows/*.yml"""
        pass
    
    def generate_databricks_resources(self) -> None:
        """Create UC schemas, clusters, jobs"""
        pass
    
    def generate_secrets_and_accounts(self) -> None:
        """Create service account + secret scope"""
        pass
    
    def generate_monitoring_dashboard(self) -> str:
        """Create Databricks dashboard"""
        pass
```

**Implementation** (see detailed section below):
- Uses Jinja2 templates in `app/templates/` directory
- Template variables from project config
- All generated code follows PEP 8 + type hints
- All generated tests are pytest-compatible

### 5. State Machine Pattern

**Pattern**: Model lifecycle states as explicit state machine

```python
class ModelLifecycleState(Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"

class ModelStateMachine:
    """Enforce valid state transitions"""
    
    VALID_TRANSITIONS = {
        DEVELOPMENT: [TESTING],
        TESTING: [STAGING],
        STAGING: [PRODUCTION, DEVELOPMENT],
        PRODUCTION: [PRODUCTION, ARCHIVED],  # Update or archive
        ARCHIVED: []
    }
    
    def transition(self, model_id: str, new_state: ModelLifecycleState) -> bool:
        """Check if transition valid"""
        current = get_model_state(model_id)
        return new_state in self.VALID_TRANSITIONS[current]
```

### 6. Approval Chain Pattern

**Pattern**: Declarative approval gates + signatures

```python
class ApprovalGate:
    """Single approval requirement"""
    gate_name: str
    required_count: int  # How many approvals needed
    required_group: str  # Which user group
    approval_method: str  # manual or automatic
    
    def check_passed(self, approval_record: ApprovalRecord) -> bool:
        """Is this gate satisfied?"""
        return len(approval_record.approvals) >= self.required_count

class ApprovalChain:
    """Multiple gates for model promotion"""
    
    def __init__(self, gates: List[ApprovalGate]):
        self.gates = gates
    
    def all_approved(self, approval_record: ApprovalRecord) -> bool:
        """All gates satisfied?"""
        return all(gate.check_passed(approval_record) for gate in self.gates)
    
    def next_pending(self) -> Optional[ApprovalGate]:
        """Which gate needs approval?"""
        pass
```

---

## Feature Implementation Specifications

### Feature 1: Setup Interview (Initial App Configuration)

**Screens**: 3 screens (see wireframes)
1. Organization info + regulated industry
2. Deployment pattern (single, dual, multi-cloud)
3. Personas & RBAC groups

**Implementation Steps**:
1. Create `app/pages/01_setup.py` Streamlit page
2. Store responses in `mlops.installation_config` UC table
3. On completion, auto-generate:
   - UC catalog structure (mlops, feature_store, data, archive)
   - All state management tables
   - GitHub org setup (if not exists)
   - Databricks resources (clusters, warehouses)
   - Service accounts + secrets
   - RBAC groups in Databricks

**Code Structure**:
```python
# app/setup/interview.py
class SetupInterview:
    def run(self) -> Dict[str, Any]:
        """Run setup interview, return config"""
        pass

# app/setup/generator.py
class SetupGenerator:
    def generate_infrastructure(self, config: Dict) -> None:
        """Create all infrastructure"""
        pass
```

**Validation**:
- Organization name: required, 3-100 chars
- Industry: required (or "None")
- Deployment pattern: required
- Personas: at least 2 groups required (data_scientists, admin)

---

### Feature 2: Project Creation Interview (7-Step Wizard)

**Screens**: 7 screens (see wireframes)
- Step 1: Basics (name, problem, success metric, owner, team)
- Step 2: Use Cases (data_ingestion, online_model, batch_model, lookup_service) - MULTI-SELECT
- Step 3: Data specifications (location, target, features, PII)
- Step 4: Governance (fairness, data quality)
- Step 5: Deployment (retraining, rollback, canary)
- Step 6: Monitoring (alerts, thresholds, destinations)
- Step 7: Governance gates (approvals, testing)
- Step 8: Review & create

**Implementation Steps**:
1. Create `app/pages/02_new_project.py` Streamlit page
2. Implement `InterviewStep` base class + 8 subclasses
3. Store responses in `mlops.projects` + `mlops.project_configurations`
4. On completion, trigger `ProjectGenerator`

**Use Case Handling**:
```python
class DataIngestionConfig:
    source_type: str  # API, database, file, streaming
    frequency: str  # hourly, daily, weekly, monthly
    schema_url: str  # Optional schema definition

class OnlineModelConfig:
    latency_ms: int  # P95 target
    uptime_pct: float  # Target uptime
    qps: int  # Expected queries per second

class BatchModelConfig:
    frequency: str  # hourly, daily, weekly, monthly
    job_timeout_hours: int

class LookupServiceConfig:
    request_fields: List[str]  # Keys to query
    response_fields: List[str]  # Values to return
    key_fields: List[str]  # Lookup keys
```

**Collapsible Sections**:
- Check if all fields in section have valid defaults
- If yes: show "Using defaults unless overridden"
- If no: show expanded by default
- Allow expand/collapse by clicking section header
- Show "✓ Matches org standard" vs "⚠️ Differs from org standard"

**Code Structure**:
```python
# app/interview/steps.py
class InterviewStep1Basics(InterviewStep):
    def __init__(self):
        self.questions = [
            Question("project_name", "What's the name...", ...),
            ...
        ]

# app/interview/builder.py
class InterviewBuilder:
    def build(self) -> InterviewWizard:
        """Construct the interview"""
        pass
```

---

### Feature 3: Data Contract Manager

**Screens**: 1 main screen (see wireframes)
- Table view of all columns
- Click row to expand details
- Options: Add column, Edit selected, Import CSV, View JSON, Commit changes

**Implementation Steps**:
1. Create `app/pages/03_data_contracts.py`
2. Implement `DataContractEditor` class
3. Support 3 creation modes:
   - **From scratch**: Manual column entry
   - **Import CSV**: Parse, auto-detect types, confirm
   - **From table**: Schema inference + LLM suggestions
4. Store in `mlops.data_contracts` + `mlops.data_contract_columns`
5. Version history in `mlops.data_contract_versions`
6. Git commit on save

**LLM Integration** (for field suggestions):
```python
class ContractLLM:
    """Use LLM cluster to suggest fields"""
    
    def suggest_descriptions(self, columns: List[str], sample_data: DataFrame) -> Dict[str, str]:
        """Suggest column descriptions"""
        prompt = f"""
        Given these columns: {columns}
        And sample data: {sample_data.head()}
        
        Provide concise, helpful descriptions for each column (1-2 sentences).
        """
        pass
    
    def suggest_pii_levels(self, columns: List[str], sample_data: DataFrame) -> Dict[str, str]:
        """Suggest PII levels: none, low, medium, high"""
        pass
    
    def suggest_classifications(self, columns: List[str]) -> Dict[str, str]:
        """Suggest classifications: public, internal, sensitive, restricted"""
        pass
```

**Quality Rules Generation**:
```python
def generate_quality_rules_for_column(column_name: str, dtype: str, sample_data: Series) -> Dict:
    """Auto-generate quality rules based on data type and distribution"""
    
    if dtype == "int" or dtype == "float":
        return {
            "null_check": {"max_null_pct": 5.0},
            "range_check": {"min": sample_data.min(), "max": sample_data.max()},
            "outlier_detection": {"method": "iqr", "threshold": 3.0}
        }
    
    elif dtype == "string":
        return {
            "null_check": {"max_null_pct": 5.0},
            "uniqueness_check": {"must_be_unique": sample_data.nunique() == len(sample_data)},
            "format_check": {"pattern": infer_pattern(sample_data)}
        }
    
    # ... more types
```

**CSV Import Flow**:
1. Upload CSV file
2. Parse + detect dtypes
3. Show confirmation screen (columns, types)
4. DS confirms
5. Create contract from CSV

**Table Inference Flow**:
1. DS specifies table path
2. Query schema
3. Sample 1000 rows
4. Auto-detect types
5. Call LLM for suggestions (descriptions, PII, classification)
6. Show confirmation screen
7. DS reviews + confirms
8. Create contract

**Git Commit**:
- On "Commit changes", export contract to JSON
- Commit to GitHub repo: `contracts/{contract_name}.json`
- Store commit hash in UC
- Version number incremented
- Change description captured

---

### Feature 4: Project Dashboard (One-Stop Shop)

**Screen**: Main landing page when you open project

**Sections**:
1. **Quick Stats**
   - Current model version (with tag: current, shadow, canary, previous)
   - Staging model (if exists)
   - Latest metrics (AUC, accuracy, latency, cost)
   - Alerts (last 7 days)

2. **Tabs**
   - Overview (quick stats, recent alerts)
   - Performance (metrics, trends, comparisons)
   - Data Quality (quality scores, drift detection)
   - Governance (approvals, audit logs)
   - Cost (spend breakdown, budget)

3. **Quick Links**
   - GitHub repo
   - MLflow registry
   - Data contracts
   - Configuration
   - Development templates
   - Monitoring dashboard

**Implementation**:
```python
# app/pages/04_project_dashboard.py
class ProjectDashboard:
    def __init__(self, project_id: str):
        self.project_id = project_id
    
    def render_tabs(self) -> None:
        """Render tabbed interface"""
        tabs = st.tabs(["Overview", "Performance", "Data Quality", "Governance", "Cost"])
        
        with tabs[0]:
            self.render_overview_tab()
        
        with tabs[1]:
            self.render_performance_tab()
        
        # ... more tabs
```

---

### Feature 5: Model Performance Monitoring

**Implementation**:
```python
class ModelMonitoring:
    """Track model performance over time"""
    
    def calculate_metrics(self, version_id: str, window: str = "last_24h") -> Dict:
        """
        Calculate all metrics for model
        window: "last_1h", "last_24h", "last_7d", "last_30d", "all_time"
        """
        pass
    
    def detect_drift(self, version_id: str, field_name: str) -> DriftResult:
        """
        Detect data drift in specific field
        Returns: DriftResult(detected, ks_stat, severity)
        """
        pass
    
    def compare_versions(self, version_id_1: str, version_id_2: str) -> ComparisonResult:
        """Compare two model versions"""
        pass
```

**Metrics to Calculate**:
- Accuracy, precision, recall, F1 (if labels available)
- AUC-ROC, AUC-PR
- Latency (p50, p95, p99)
- Error rate
- Inference volume (QPS or daily count)
- Data drift (KS statistic per field)
- Quality scores (per field)
- Fairness metrics (demographic parity, equalized odds)
- Calibration

**Drift Detection**:
```python
def detect_data_drift(baseline_data: Series, current_data: Series, threshold: float = 0.1) -> Tuple[bool, float]:
    """
    Kolmogorov-Smirnov test for data drift
    Returns: (drift_detected, ks_statistic)
    """
    from scipy.stats import ks_2samp
    
    statistic, p_value = ks_2samp(baseline_data, current_data)
    drift_detected = statistic > threshold
    
    return drift_detected, statistic
```

---

### Feature 6: Approval System

**Implementation**:
```python
class ApprovalManager:
    """Manage approval workflows"""
    
    def request_approval(self, model_id: str, gate_type: str, required_group: str, required_count: int) -> str:
        """Create approval request"""
        pass
    
    def submit_approval(self, approval_id: str, decision: str, comment: str, user_email: str) -> None:
        """Submit approval decision (approve/reject/request_changes)"""
        pass
    
    def get_pending_approvals(self, user_email: str) -> List[ApprovalRecord]:
        """Get approvals waiting for this user"""
        pass
    
    def check_gate_passed(self, approval_id: str, gate_type: str) -> bool:
        """Is this gate satisfied?"""
        pass
```

**Approval Decisions**:
- ✓ Approve (user confirms)
- 🔄 Request Changes (ask for modifications)
- ✗ Reject (deny promotion)

**Captured Data**:
- Approver email
- Timestamp
- IP address
- Comments
- Approval decision
- All stored in `mlops.approvals` table

---

### Feature 7: Secrets & Service Account Management

**Implementation**:
```python
class SecretsManager:
    """Manage secrets and service accounts"""
    
    def create_service_account(self, project_id: str, workspace_id: str) -> str:
        """Create service account: sa-{model_id}-{workspace}"""
        pass
    
    def create_secrets(self, project_id: str, scope_name: str) -> Dict[str, str]:
        """Create secrets in Databricks Secret Scope"""
        secrets = {
            "databricks_token": generate_pat(),
            "databricks_token_training": generate_pat(),
            "github_token": github_pat()
        }
        # Store in Databricks Secret Scope
        pass
    
    def rotate_secret(self, secret_id: str) -> None:
        """Rotate a secret"""
        # 1. Generate new secret
        # 2. Test new secret (run test job)
        # 3. If test passes: deploy new secret
        # 4. After 7-day grace period: revoke old secret
        pass
    
    def get_rotation_schedule(self, project_id: str) -> Dict:
        """Get rotation schedule for all secrets"""
        pass
```

**Rotation Process**:
1. Generate new secret
2. Deploy to staging job
3. Run test job with new secret
4. If test passes: update production
5. Keep old secret for 7 days (grace period)
6. Revoke old secret
7. Log all steps in audit trail

---

### Feature 8: CI/CD Pipeline Generation

**Implementation** (generates .github/workflows/*.yml):
```python
class CIPipelineGenerator:
    """Generate GitHub Actions workflows"""
    
    def __init__(self, project_config: ProjectConfig):
        self.config = project_config
    
    def generate_lint_pipeline(self) -> str:
        """Generate lint.yml: pylint, black, isort, mypy, pydocstyle"""
        pass
    
    def generate_security_pipeline(self) -> str:
        """Generate security.yml: pip-audit"""
        pass
    
    def generate_test_pipeline(self) -> str:
        """Generate test.yml: pytest (100% coverage required)"""
        pass
    
    def generate_model_validation_pipeline(self) -> str:
        """Generate model-validation.yml: train, evaluate, fairness tests"""
        pass
    
    def generate_deploy_staging_pipeline(self) -> str:
        """Generate deploy-staging.yml: register to MLflow, deploy to endpoint"""
        pass
    
    def generate_deploy_prod_pipeline(self) -> str:
        """Generate deploy-prod.yml: (manual trigger) production deployment"""
        pass
```

**Pipeline Requirements**:

**lint.yml**:
- pylint src/ --fail-under=8.0
- black --check src/
- isort --check-only src/
- mypy src/ --strict
- pydocstyle src/
- Check for unused variables

**security.yml**:
- pip-audit --desc (fail on critical)

**test.yml**:
- pytest tests/unit -v --cov=src --cov-fail-under=100
- pytest tests/integration -v
- Upload coverage to codecov

**model-validation.yml**:
- Train model on test data
- Validate accuracy >= threshold
- Run fairness tests (aif360 or fairlearn)
- Regression test vs baseline

**deploy-staging.yml** (auto-trigger on merge to main):
- Register model to MLflow Staging
- Deploy to Model Serving endpoint (staging)
- Run end-to-end test
- Set tag: "staging"

**deploy-prod.yml** (manual trigger):
- Register model to MLflow Production
- Set tag: "current" (on new version)
- Set tag: "previous" (on old version)
- Deploy to Model Serving endpoint (prod)
- Start monitoring

---

### Feature 9: Template Generation

**Skeleton Code Generation**:

```python
class SkeletonCodeGenerator:
    """Generate training skeleton code"""
    
    def generate_train_py(self) -> str:
        """Generate src/train.py"""
        template = load_template("train.py.jinja2")
        
        context = {
            "model_name": self.config.project_name,
            "model_type": self.config.model_type,  # Inferred from code, not asked
            "features": self.config.feature_columns,
            "target": self.config.target_variable,
            "mlflow_experiment": self.config.mlflow_experiment_name,
            "fairness_attributes": self.config.fairness_attributes,
            "bias_test_type": self.config.bias_test_type,
        }
        
        return template.render(**context)
    
    def generate_preprocess_py(self) -> str:
        """Generate src/preprocess.py with data quality checks"""
        pass
    
    def generate_evaluate_py(self) -> str:
        """Generate src/evaluate.py with fairness tests"""
        pass
    
    def generate_inference_py(self) -> str:
        """Generate src/inference.py for Model Serving"""
        pass
    
    def generate_config_py(self) -> str:
        """Generate src/config.py with all interview responses"""
        pass
    
    def generate_test_files(self) -> Dict[str, str]:
        """Generate test_*.py files"""
        # test_preprocess.py - data validation tests
        # test_evaluate.py - performance tests
        # test_fairness.py - fairness tests
        # test_pipeline.py - end-to-end tests
        pass
    
    def generate_notebooks(self) -> Dict[str, str]:
        """Generate Jupyter notebooks"""
        # 01_EDA.ipynb - exploratory analysis skeleton
        # 02_Feature_Engineering.ipynb - feature engineering skeleton
        # 03_Train.ipynb - training notebook
        # 04_Evaluate.ipynb - evaluation notebook
        pass
    
    def generate_makefile(self) -> str:
        """Generate Makefile for common tasks"""
        pass
    
    def generate_devcontainer(self) -> str:
        """Generate .devcontainer.json for VS Code"""
        pass
    
    def generate_requirements_txt(self) -> str:
        """Generate requirements.txt with pinned versions"""
        base_deps = [
            f"mlflow=={MLFLOW_VERSION}",
            f"databricks-sdk=={DATABRICKS_SDK_VERSION}",
            "pytest>=7.0",
            "black>=22.0",
            "isort>=5.0",
            "pylint>=2.0",
            "mypy>=0.9",
            "pydocstyle>=6.0",
            "pip-audit>=2.0"
        ]
        
        if self.config.model_type == "xgboost":
            base_deps.append(f"xgboost=={XGBOOST_VERSION}")
        elif self.config.model_type == "sklearn":
            base_deps.append(f"scikit-learn=={SKLEARN_VERSION}")
        # ... more frameworks
        
        if self.config.fairness_enabled:
            base_deps.append(f"aif360=={AIF360_VERSION}")  # or fairlearn
        
        return "\n".join(base_deps)
```

**Template Files** (in `app/templates/`):
- `train.py.jinja2` - Main training script
- `preprocess.py.jinja2` - Data processing
- `evaluate.py.jinja2` - Model evaluation + fairness
- `inference.py.jinja2` - Model serving code
- `config.py.jinja2` - Config and hyperparameters
- `test_*.py.jinja2` - Test skeletons
- `notebooks/*.ipynb.jinja2` - Notebook skeletons
- `Makefile.jinja2` - Make tasks
- `.devcontainer.json.jinja2` - VS Code container config
- `.github/workflows/*.yml.jinja2` - CI/CD pipelines
- `README.md.jinja2` - Project README
- `CONTRIBUTING.md.jinja2` - Contribution guidelines
- `docs/MODEL_CARD.md.jinja2` - Model card template
- `docs/ARCHITECTURE.md.jinja2` - Architecture doc
- `docs/RUNBOOK.md.jinja2` - Operations runbook

---

## API Specifications

All APIs are accessed through **Databricks Model Serving** (built into MLflow).

### Model Serving Endpoints

**For Batch Models**:
- Inference scheduled via Databricks Workflows
- Results written to output table

**For Online Models**:
- REST endpoint exposed via Model Serving
- URL: `https://{workspace-url}/serving-endpoints/{model_name}`
- Auth: Databricks PAT token

**For Lookup Services**:
- REST endpoint returning key-value pairs
- Request: `POST /serving-endpoints/{lookup_service}/invocations`
- Body:
  ```json
  {
    "dataframe_records": [
      {
        "key_field_1": "value1",
        "key_field_2": "value2"
      }
    ]
  }
  ```
- Response:
  ```json
  {
    "predictions": [
      {
        "key_field_1": "value1",
        "key_field_2": "value2",
        "response_field_1": "result1",
        "response_field_2": "result2"
      }
    ]
  }
  ```

### Databricks SDK APIs (Used by App)

**Project Creation**:
```python
# Not a REST API, but Python SDK calls
from databricks.sdk import WorkspaceClient

client = WorkspaceClient()

# Create UC schemas
client.catalogs.create(Catalog(name="mlops"))
client.schemas.create(CreateSchema(catalog_name="mlops", name="models"))

# Create service account
response = client.service_principals.create(ServicePrincipal(display_name=f"sa-{model_id}"))

# Create secret scope
client.secrets.create_scope(Scope(scope=secret_scope_name))

# Create secret
client.secrets.put_secret(scope=secret_scope_name, key=secret_name, string_value=secret_value)
```

**Model Registry**:
```python
import mlflow

# Register model
mlflow.register_model(model_uri=f"runs:/{run_id}/model", name=model_name)

# Set model stage
client = mlflow.tracking.MlflowClient()
client.transition_model_version_stage(name=model_name, version=version, stage="Staging")

# Add tag
client.set_model_version_tag(name=model_name, version=version, key="current", value="true")
```

**Data Operations**:
```python
from databricks.sdk.service.sql import StatementExecutionApi

# Execute SQL against UC
response = sql_api.statement(
    warehouse_id=warehouse_id,
    statement="SELECT * FROM mlops.projects WHERE status='production'"
).result()

# Load table as Spark DataFrame
df = spark.read.table("mlops.projects")

# Write to UC table
df.write.mode("append").option("mergeSchema", "true").saveAsTable("mlops.audit_logs")
```

---

## Frontend Implementation Details

### Streamlit App Structure

```
app/
├── streamlit_config.toml           # Streamlit configuration
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variables template
│
├── main.py                         # Entry point, sidebar navigation
│
├── pages/
│   ├── 01_setup.py                # Initial setup/configuration
│   ├── 02_new_project.py           # New project creation (7-step interview)
│   ├── 03_projects.py              # List all projects
│   ├── 04_project_dashboard.py     # Single project dashboard (main view)
│   ├── 05_data_contracts.py        # Data contract manager
│   ├── 06_approvals.py             # Approval center
│   ├── 07_monitoring.py            # Monitoring & alerts dashboard
│   ├── 08_templates.py             # Development templates
│   ├── 09_settings.py              # Admin settings
│   └── 10_documentation.py         # Help & documentation
│
├── components/
│   ├── interview_wizard.py         # Reusable interview component
│   ├── metric_card.py              # Card showing metric + status
│   ├── approval_widget.py          # Approval decision widget
│   ├── drift_chart.py              # Drift visualization
│   ├── model_comparison.py         # Compare two model versions
│   └── help_tooltips.py            # Help text on hover
│
├── utils/
│   ├── databricks_client.py        # Databricks API wrapper
│   ├── mlflow_client.py            # MLflow API wrapper
│   ├── github_client.py            # GitHub API wrapper
│   ├── state_manager.py            # Session state management
│   ├── config_loader.py            # Load configuration
│   ├── constants.py                # Global constants
│   └── helpers.py                  # Utility functions
│
├── services/
│   ├── project_service.py          # Project CRUD operations
│   ├── interview_service.py        # Interview logic
│   ├── generator_service.py        # Auto-generation logic
│   ├── monitoring_service.py       # Monitoring calculations
│   ├── approval_service.py         # Approval workflows
│   └── validation_service.py       # Data validation
│
├── templates/                      # Jinja2 templates for code generation
│   ├── train.py.jinja2
│   ├── preprocess.py.jinja2
│   ├── evaluate.py.jinja2
│   ├── inference.py.jinja2
│   ├── config.py.jinja2
│   ├── conftest.py.jinja2
│   ├── Makefile.jinja2
│   ├── .devcontainer.json.jinja2
│   ├── .github/workflows/lint.yml.jinja2
│   ├── .github/workflows/test.yml.jinja2
│   ├── .github/workflows/model_validation.yml.jinja2
│   ├── .github/workflows/deploy_staging.yml.jinja2
│   ├── .github/workflows/deploy_prod.yml.jinja2
│   ├── README.md.jinja2
│   ├── docs/MODEL_CARD.md.jinja2
│   ├── docs/RUNBOOK.md.jinja2
│   └── ... more templates
│
└── tests/
    ├── test_interview.py
    ├── test_generator.py
    ├── test_monitoring.py
    ├── test_approval_logic.py
    └── conftest.py
```

### Key Streamlit Patterns

**Session State Management**:
```python
# Initialize session state
if "current_step" not in st.session_state:
    st.session_state.current_step = 1

if "interview_data" not in st.session_state:
    st.session_state.interview_data = {}

# Update state on user input
st.session_state.interview_data["project_name"] = st.text_input(...)
```

**Collapsible Sections**:
```python
# Check if all fields have defaults
all_defaults_valid = all(field.has_default and not field.required for field in section.questions)

# Use expander
with st.expander(f"▶ {section_title}", expanded=not all_defaults_valid):
    if all_defaults_valid:
        st.info("✓ Using defaults unless overridden")
    
    # Render questions
    for question in section.questions:
        question.render(st.session_state)
```

**Tabbed Interface**:
```python
tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Performance", "Data Quality", "Governance"])

with tab1:
    render_overview_tab()

with tab2:
    render_performance_tab()

# ... more tabs
```

**Markdown for Explainers**:
```python
st.markdown("""
### Personas & Groups

This section defines which groups of users, based on their Unity Catalog 
permission group membership, will have specific permissions within the platform.

**Key Points:**
- Users might have membership in more than one group
- Permissions are cumulative (user can do anything any of their groups can do)
- Groups are defined in your Databricks workspace
""")
```

---

## Backend Implementation Details

### Databricks Integration

**Workspace Client Setup**:
```python
from databricks.sdk import WorkspaceClient

class DatabricksManager:
    def __init__(self, workspace_url: str, token: str):
        self.client = WorkspaceClient(
            host=workspace_url,
            token=token
        )
    
    def create_schema(self, catalog: str, schema: str) -> None:
        """Create UC schema"""
        self.client.schemas.create(
            CreateSchema(catalog_name=catalog, name=schema)
        )
    
    def query_table(self, table_name: str, sql: str) -> List[Dict]:
        """Query UC table"""
        # Use SQL warehouse to execute query
        pass
    
    def write_table(self, df: DataFrame, table_name: str, mode: str = "append") -> None:
        """Write to UC table"""
        df.write.mode(mode).option("mergeSchema", "true").saveAsTable(table_name)
```

**MLflow Integration**:
```python
import mlflow
from mlflow.tracking import MlflowClient

class MLflowManager:
    def __init__(self, tracking_uri: str):
        self.client = MlflowClient(tracking_uri)
        mlflow.set_tracking_uri(tracking_uri)
    
    def register_model(self, model_uri: str, model_name: str) -> None:
        """Register model to MLflow"""
        mlflow.register_model(model_uri, model_name)
    
    def set_model_stage(self, model_name: str, version: int, stage: str) -> None:
        """Transition model to new stage"""
        self.client.transition_model_version_stage(
            name=model_name,
            version=version,
            stage=stage
        )
    
    def add_model_tag(self, model_name: str, version: int, key: str, value: str) -> None:
        """Add tag to model version"""
        self.client.set_model_version_tag(model_name, version, key, value)
```

**GitHub Integration**:
```python
from github import Github

class GitHubManager:
    def __init__(self, token: str):
        self.github = Github(token)
    
    def create_repo(self, org_name: str, repo_name: str, description: str) -> str:
        """Create new repository"""
        org = self.github.get_organization(org_name)
        repo = org.create_repo(
            name=repo_name,
            description=description,
            private=True,
            auto_init=True
        )
        return repo.clone_url
    
    def add_files_to_repo(self, org_name: str, repo_name: str, files: Dict[str, str]) -> None:
        """Add files to repo"""
        repo = self.github.get_user().get_repo(repo_name)
        
        for file_path, content in files.items():
            try:
                repo.create_file(
                    path=file_path,
                    message=f"Add {file_path}",
                    content=content
                )
            except:
                # File already exists, update it
                contents = repo.get_contents(file_path)
                repo.update_file(
                    path=file_path,
                    message=f"Update {file_path}",
                    content=content,
                    sha=contents.sha
                )
    
    def configure_branch_protection(self, org_name: str, repo_name: str) -> None:
        """Set up branch protection on main"""
        repo = self.github.get_user().get_repo(repo_name)
        
        repo.get_branch("main").edit_protection(
            required_status_checks=RequiredStatusChecks(...),
            required_pull_request_reviews=RequiredPullRequestReviewsConstraints(
                required_approving_review_count=2,
                dismiss_stale_reviews=True
            ),
            enforce_admins=True,
            allow_force_pushes=False,
            allow_deletions=False
        )
```

---

## Integration Points

### 1. Databricks Workspace Connection

**Entry Point**: On app load, check for Databricks connection

```python
# app/utils/databricks_client.py
def get_workspace_client() -> WorkspaceClient:
    """Get Databricks workspace client"""
    # Try to get from secrets
    if "DATABRICKS_HOST" in os.environ and "DATABRICKS_TOKEN" in os.environ:
        return WorkspaceClient(...)
    
    # Else prompt user
    st.error("Please set DATABRICKS_HOST and DATABRICKS_TOKEN environment variables")
    st.stop()
```

### 2. MLflow Connection

MLflow automatically points to workspace MLflow by default.

```python
mlflow.set_tracking_uri("databricks")
```

### 3. GitHub Connection

Required for repository creation. Store token in Databricks Secret Scope.

```python
github_token = client.secrets.get_secret(scope="mlops-admin", key="github_token")
github = Github(github_token)
```

### 4. Data Flow

```
Interview → Config JSON → Generator → 
  GitHub Repo Creation +
  UC Tables + 
  Service Accounts +
  CI/CD Pipelines +
  Skeleton Code +
  Monitoring Dashboard
```

---

## Testing Strategy

### Unit Tests

**Location**: `app/tests/`

**Coverage**: 100% required (pytest with coverage)

```python
# app/tests/test_interview.py
def test_interview_step_validation():
    """Test interview step validation"""
    step = InterviewStep1Basics()
    
    # Invalid: empty project name
    st.session_state.interview_data["project_name"] = ""
    assert not step.validate()
    
    # Valid
    st.session_state.interview_data["project_name"] = "valid_name"
    assert step.validate()

# app/tests/test_generator.py
def test_generate_train_py():
    """Test skeleton code generation"""
    config = ProjectConfig(
        project_name="test_model",
        model_type="xgboost",
        features=["age", "income"],
        target="churn"
    )
    
    generator = SkeletonCodeGenerator(config)
    code = generator.generate_train_py()
    
    assert "import xgboost" in code
    assert "xgboost.train" in code
    assert "mlflow.log_metric" in code

# app/tests/test_monitoring.py
def test_detect_drift():
    """Test drift detection"""
    baseline = np.array([1, 2, 3, 4, 5])
    current = np.array([2, 3, 4, 5, 6])
    
    drift_detected, ks_stat = detect_data_drift(baseline, current, threshold=0.2)
    
    assert not drift_detected  # KS stat < threshold
    assert ks_stat < 0.2
```

### Integration Tests

**Location**: `app/tests/integration/`

```python
# Test full workflow
def test_full_project_creation_flow():
    """Test creating a project end-to-end"""
    
    # 1. Run interview
    interview = ProjectInterview()
    config = interview.run_all_steps()
    
    # 2. Generate infrastructure
    generator = ProjectGenerator(config)
    generator.generate_github_repo()
    generator.generate_databricks_resources()
    
    # 3. Verify UC tables created
    result = workspace_client.sql("SELECT COUNT(*) FROM mlops.projects WHERE project_name='{}'".format(config.project_name))
    assert result[0][0] == 1
    
    # 4. Verify GitHub repo exists
    repo = github.get_user().get_repo(config.github_repo_name)
    assert repo is not None
    
    # 5. Verify CI/CD workflows exist
    workflows = repo.get_contents(".github/workflows")
    assert any(w.name.startswith("lint") for w in workflows)
    assert any(w.name.startswith("test") for w in workflows)
```

### Test Data

Create fixtures for:
- Sample project configs
- Sample models (trained sklearn/xgboost)
- Sample data (normal + drifted distributions)
- Sample approvals (different states)

---

## Deployment & Operations

### Deployment Options

**Option 1: Databricks Workspace App** (Native)
```bash
# Deploy as native Databricks App
databricks apps publish \
  --source-code-path ./app \
  --deployment-id production \
  --workspace-url <workspace-url>
```

**Option 2: Docker Container** (Portable)
```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "main.py"]
```

**Option 3: Kubernetes** (Enterprise)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlops-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mlops-app
  template:
    metadata:
      labels:
        app: mlops-app
    spec:
      containers:
      - name: mlops-app
        image: mlops-app:latest
        ports:
        - containerPort: 8501
        env:
        - name: DATABRICKS_HOST
          valueFrom:
            secretKeyRef:
              name: databricks-secrets
              key: host
        - name: DATABRICKS_TOKEN
          valueFrom:
            secretKeyRef:
              name: databricks-secrets
              key: token
```

### Monitoring & Logging

**App Logging**:
```python
import logging

logger = logging.getLogger(__name__)

logger.info(f"Project {project_id} created successfully")
logger.error(f"Failed to generate GitHub repo: {error}", exc_info=True)
```

**Databricks Workflow Logging**:
- All job outputs logged to Databricks
- Accessible from workspace UI
- Searchable in audit logs

### Health Checks

```python
@app.route("/health")
def health_check():
    """Check app health"""
    try:
        # Check Databricks connection
        workspace_client.get_workspace(path="/")
        
        # Check MLflow connection
        mlflow.search_experiments()
        
        # Check GitHub connection
        github.get_user()
        
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500
```

---

## File Structure & Codebase Organization

```
databricks-mlops-app/
│
├── README.md                       # Project overview + getting started
├── CONTRIBUTING.md                 # Contribution guidelines
├── LICENSE                         # Open source license (Apache 2.0)
├── setup.py                        # Package setup
├── requirements.txt                # Python dependencies
├── pyproject.toml                  # Project config (lint, pytest)
│
├── .github/
│   └── workflows/
│       ├── tests.yml              # Run tests on PR
│       ├── lint.yml               # Linting checks
│       ├── security.yml           # Security scanning
│       └── release.yml            # Release process
│
├── .env.example                    # Environment variables template
├── .gitignore                      # Git ignore rules
├── .pre-commit-config.yaml         # Pre-commit hooks
│
├── app/                            # Streamlit app
│   ├── main.py                    # Entry point
│   ├── streamlit_config.toml       # Streamlit configuration
│   │
│   ├── pages/
│   │   ├── 01_setup.py
│   │   ├── 02_new_project.py
│   │   ├── 03_projects.py
│   │   ├── 04_project_dashboard.py
│   │   ├── 05_data_contracts.py
│   │   ├── 06_approvals.py
│   │   ├── 07_monitoring.py
│   │   ├── 08_templates.py
│   │   ├── 09_settings.py
│   │   └── 10_documentation.py
│   │
│   ├── components/
│   │   ├── __init__.py
│   │   ├── interview_wizard.py
│   │   ├── metric_card.py
│   │   ├── approval_widget.py
│   │   ├── drift_chart.py
│   │   └── ...
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── project_service.py
│   │   ├── interview_service.py
│   │   ├── generator_service.py
│   │   ├── monitoring_service.py
│   │   ├── approval_service.py
│   │   └── ...
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── databricks_client.py
│   │   ├── mlflow_client.py
│   │   ├── github_client.py
│   │   ├── state_manager.py
│   │   ├── constants.py
│   │   └── ...
│   │
│   ├── templates/                 # Jinja2 templates
│   │   ├── train.py.jinja2
│   │   ├── preprocess.py.jinja2
│   │   ├── evaluate.py.jinja2
│   │   ├── Makefile.jinja2
│   │   ├── .github/workflows/lint.yml.jinja2
│   │   └── ...
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_interview.py
│       ├── test_generator.py
│       ├── test_monitoring.py
│       └── ...
│
├── mlops_toolkit/                  # Agnostic MLOps logic
│   ├── __init__.py
│   ├── data/
│   │   ├── contracts.py           # Data contract validation
│   │   ├── quality.py             # Data quality assessment
│   │   ├── drift.py               # Drift detection
│   │   └── versioning.py          # Data versioning
│   │
│   ├── model/
│   │   ├── fairness.py            # Fairness testing (aif360, fairlearn)
│   │   ├── validation.py          # Model validation
│   │   └── monitoring.py          # Performance monitoring
│   │
│   ├── ci_cd/
│   │   ├── pipeline_generator.py  # CI/CD pipeline generation
│   │   ├── templates.py           # Code generation templates
│   │   └── validation.py          # Pipeline validation
│   │
│   └── tests/
│       ├── test_data_quality.py
│       ├── test_fairness.py
│       └── ...
│
├── docs/
│   ├── architecture.md            # System architecture
│   ├── database_schema.md          # UC table definitions
│   ├── api_reference.md           # API documentation
│   ├── getting_started.md         # Quick start guide
│   ├── development.md             # Development setup
│   └── deployment.md              # Deployment guide
│
└── examples/
    ├── simple_batch_model/        # Example projects
    ├── online_model_serving/
    ├── lookup_service/
    └── data_ingestion_pipeline/
```

---

## Dependencies & Prerequisites

### Databricks Requirements

- ✅ Databricks workspace (AWS/Azure/GCP)
- ✅ Unity Catalog enabled
- ✅ SQL warehouse or all-purpose cluster
- ✅ MLflow tracking URI set to workspace MLflow
- ✅ Model Serving enabled

### GitHub Requirements

- ✅ GitHub organization (personal account ok for testing)
- ✅ GitHub Personal Access Token (repo, workflow scopes)
- ✅ GitHub Actions enabled

### Python Dependencies

**Core**:
- `databricks-sdk>=0.9.0`
- `mlflow>=2.0.0`
- `streamlit>=1.28.0`
- `plotly>=5.0.0`
- `pyyaml>=6.0`
- `jinja2>=3.0`
- `PyGithub>=1.59.0`

**Data**:
- `pandas>=1.5.0`
- `numpy>=1.24.0`
- `polars>=0.18.0` (optional)
- `pyarrow>=12.0.0`

**ML/Fairness**:
- `scikit-learn>=1.2.0`
- `xgboost>=1.7.0`
- `lightgbm>=3.3.0`
- `aif360>=0.5.0`
- `fairlearn>=0.9.0`
- `shap>=0.42.0`
- `lime>=0.2.0`

**Testing**:
- `pytest>=7.0.0`
- `pytest-cov>=4.0.0`
- `pytest-mock>=3.10.0`

**Linting**:
- `black>=22.0.0`
- `isort>=5.11.0`
- `pylint>=2.15.0`
- `mypy>=0.991`
- `pydocstyle>=6.3.0`
- `pip-audit>=2.4.0`

**Utilities**:
- `python-dotenv>=0.21.0`
- `requests>=2.28.0`
- `scipy>=1.9.0`

---

## Implementation Timeline & Milestones

### Phase 1: Foundation (Weeks 1-4)

- ✅ Set up project structure + CI/CD
- ✅ Implement Databricks/MLflow/GitHub clients
- ✅ Create UC table schemas (database_schema.md)
- ✅ Basic Streamlit app shell (main.py + sidebar)
- ✅ Unit tests framework

**Deliverable**: App runs, pages navigate, database ready

### Phase 2: Setup & Interview (Weeks 5-8)

- ✅ Setup interview (org config, deployment pattern, personas)
- ✅ Project creation interview (7-step wizard)
- ✅ Collapsible sections with defaults
- ✅ Interview validation + storage
- ✅ Unit tests for interview logic

**Deliverable**: Full interview flow working, configs stored

### Phase 3: Auto-Generation (Weeks 9-14)

- ✅ GitHub repo creation + template files
- ✅ Skeleton code generation (train.py, tests, etc.)
- ✅ CI/CD pipeline generation
- ✅ Databricks resource creation (schemas, clusters, jobs)
- ✅ Service account + secrets creation
- ✅ Integration tests

**Deliverable**: New project fully bootstrapped end-to-end

### Phase 4: Data Contracts (Weeks 15-18)

- ✅ Data contract manager UI
- ✅ Create from scratch / import CSV / from table flows
- ✅ LLM integration for field suggestions
- ✅ Quality rules auto-generation
- ✅ Version control + Git commits
- ✅ Contract validation logic

**Deliverable**: Data contracts fully functional

### Phase 5: Monitoring & Performance (Weeks 19-24)

- ✅ Performance monitoring calculations
- ✅ Drift detection (data + quality)
- ✅ Model performance dashboard
- ✅ Alerts configuration + history
- ✅ Field-level drift alerts
- ✅ SHAP/LIME integration

**Deliverable**: Complete performance dashboard

### Phase 6: Governance & Approvals (Weeks 25-28)

- ✅ Approval system implementation
- ✅ Approval center UI
- ✅ Signature + audit capture
- ✅ RBAC enforcement
- ✅ Segregation of duties checks

**Deliverable**: Approval workflows working, SOX-compliant

### Phase 7: Polish & Documentation (Weeks 29-32)

- ✅ Error handling + edge cases
- ✅ Performance optimization
- ✅ Comprehensive documentation
- ✅ Example projects
- ✅ Deployment guide
- ✅ Contributing guidelines

**Deliverable**: Production-ready, open-source release

---

## Known Risks & Mitigation

### Risk 1: Complexity of Interview System

**Risk**: 7-step interview with many interdependencies is complex to maintain

**Mitigation**:
- ✅ Use inheritance (InterviewStep base class)
- ✅ Separate logic from UI
- ✅ Comprehensive unit tests
- ✅ Clear documentation for adding new questions

### Risk 2: Code Generation Correctness

**Risk**: Generated code could have bugs, template errors, or security issues

**Mitigation**:
- ✅ Use established Jinja2 templates
- ✅ Validate generated code (linting, type checking)
- ✅ Test all generated workflows in CI
- ✅ Version templates independently
- ✅ Manual review process for generated code

### Risk 3: Databricks API Changes

**Risk**: Databricks SDK could change, breaking app

**Mitigation**:
- ✅ Pin SDK versions in requirements.txt
- ✅ Wrap SDK calls in abstraction layer
- ✅ Monitor deprecations
- ✅ Have fallback implementations

### Risk 4: GitHub API Rate Limiting

**Risk**: Creating repos, managing workflows could hit rate limits

**Mitigation**:
- ✅ Implement exponential backoff
- ✅ Cache requests where possible
- ✅ Use GitHub organization token (higher limits)
- ✅ Queue repo creation for larger batches

### Risk 5: Scaling to Many Models

**Risk**: App could become slow with 100+ models

**Mitigation**:
- ✅ Index UC tables properly (see DATABASE_SCHEMA.md)
- ✅ Paginate lists in UI
- ✅ Cache expensive calculations
- ✅ Use projection queries (select only needed columns)

### Risk 6: State Consistency

**Risk**: Session state and UC tables getting out of sync

**Mitigation**:
- ✅ Single source of truth: UC tables
- ✅ Session state is read cache only
- ✅ Refresh session state on page load
- ✅ Use transactions where possible

---

## Implementation Checklist for Claude Code

```
FOUNDATIONAL
□ Set up GitHub repo + structure
□ Configure CI/CD (.github/workflows)
□ Create requirements.txt + pyproject.toml
□ Implement Databricks client wrapper
□ Implement MLflow client wrapper
□ Implement GitHub client wrapper
□ Create UC table schemas (DDL)

CORE INTERVIEW
□ Interview question data structure
□ InterviewStep base class
□ 7 interview step implementations
□ Interview wizard component
□ Collapsible section logic
□ Session state management
□ Interview validation

AUTO-GENERATION
□ ProjectGenerator class
□ Template loader + renderer
□ Skeleton code templates (jinja2)
□ GitHub repo creation
□ GitHub file creation/updates
□ CI/CD pipeline generation
□ Databricks resource creation
□ Service account + secrets creation

DATA CONTRACTS
□ DataContract + ContractColumn classes
□ Data contract UI editor
□ CSV import flow
□ Table inference flow
□ LLM integration for suggestions
□ Quality rule generation
□ Git commit flow for contracts

MONITORING
□ Performance metric calculations
□ Drift detection (KS test)
□ Model performance history tracking
□ Fairness metric calculations
□ Alert configuration UI
□ Alert history + execution

APPROVALS
□ ApprovalGate + ApprovalChain classes
□ Approval request creation
□ Approval decision capture
□ Signature + audit logging
□ RBAC enforcement
□ Segregation of duties checks

UI/DASHBOARDS
□ Main project dashboard
□ Performance metrics dashboard
□ Data quality dashboard
□ Governance dashboard
□ Approval center
□ Monitoring dashboard

DOCUMENTATION
□ README.md
□ API reference
□ Database schema docs
□ Development setup guide
□ Deployment guide
□ Example projects

TESTING
□ Unit tests (100% coverage)
□ Integration tests
□ End-to-end workflow tests
□ Test fixtures + data
□ CI/CD integration

POLISH
□ Error handling + user messaging
□ Performance optimization
□ Security review
□ Accessibility review
□ Documentation completeness
□ Example projects working
```

---

## Success Criteria

✅ **App launches successfully** in Databricks workspace

✅ **Full interview flow** completes without errors (7 steps)

✅ **Auto-generation works end-to-end**: GitHub repo + skeleton code + CI/CD

✅ **Data contracts** can be created, versioned, and validated

✅ **Project dashboard** shows real model metrics + alerts

✅ **Approval workflows** enforce RBAC + capture signatures

✅ **Tests pass** (100% unit coverage, integration tests)

✅ **Monitoring detects drift** in real data

✅ **Documentation complete** + examples working

✅ **Open source ready**: license, contributing guide, examples

