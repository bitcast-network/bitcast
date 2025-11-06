# Bitcast Validator System Architecture

## Overview

The Bitcast Validator is a sophisticated, modular system for evaluating content across multiple social media platforms and calculating rewards for miners. It maintains network integrity through comprehensive content verification, security auditing, performance optimization, and fair reward distribution across the Bitcast ecosystem.

## System Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                          Bitcast Validator System                         │
└───────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────┐    ┌─────────────────────────────┐    ┌─────────────────────┐
│ forward.py  │───▶│    RewardOrchestrator       │───▶│  Platform Evaluators │
│ Entry Point │    │   (Central Coordinator)     │    │  • YouTubeEvaluator │
│ & Lifecycle │    │                             │    │  • [Future Platforms]│
└─────────────┘    └─────────────────────────────┘    └─────────────────────┘
                                       │
                                       ▼
                   ┌─────────────────────────────────────────────────────┐
                   │                Core Services                        │
                   │                                                     │
                   │  • MinerQueryService          • PlatformRegistry    │
                   │  • ScoreAggregationService    • EmissionCalculation │
                   │  • RewardDistributionService  • ErrorHandling       │
                   └─────────────────────────────────────────────────────┘
                                       │
                                       ▼
                   ┌─────────────────────────────────────────────────────┐
                   │              Content Evaluation                     │
                   │                                                     │
                   │  • Prompt Versioning System    • Security Auditing │
                   │  • Multi-Platform Evaluation   • Performance Opts  │
                   │  • Anti-Exploitation Scoring   • Error Recovery    │
                   └─────────────────────────────────────────────────────┘
                                       │
                                       ▼
                   ┌─────────────────────────────────────────────────────┐
                   │               Supporting Systems                    │
                   │                                                     │
                   │  • LLM Router (Multi-Provider)    • Intelligent    │
                   │  • Content Briefs & Caching       • Configuration  │
                   │  • Error Handling Standards       • State Mgmt     │
                   │  • Performance Monitoring         • Stats Pub      │
                   └─────────────────────────────────────────────────────┘
                                       │
                                       ▼
                   ┌─────────────────────────────────────────────────────┐
                   │                External APIs                        │
                   │                                                     │
                   │  • YouTube Data & Analytics API   • RapidAPI       │
                   │  • OpenAI / Chutes LLM APIs        • Bitcast Server │
                   │  • Transcript Services             • Monitoring     │
                   └─────────────────────────────────────────────────────┘
```

## Core Design Principles

### 1. **Modular Architecture with Security-First Design**
- **Single Responsibility**: Each component has one clear, well-defined purpose
- **Loose Coupling**: Components interact through well-defined interfaces with error boundaries
- **High Cohesion**: Related functionality grouped logically with comprehensive error handling
- **Security Integration**: Multi-layer security auditing built into evaluation pipeline

### 2. **Platform Agnostic Core with Advanced Evaluation**
- **Extensible Design**: Easy addition of new social media platforms through standardized interfaces
- **Interface-Based**: Platform evaluators implement common evaluation patterns
- **Plugin Architecture**: Platforms register themselves with sophisticated capability detection
- **Content Security**: Prompt injection detection and content manipulation prevention

### 3. **Performance Optimized & Highly Testable**
- **Dependency Injection**: All services mockable and independently testable
- **Service-Oriented**: Business logic separated into focused, optimized services
- **Comprehensive Testing**: Unit, integration, performance, and security test coverage
- **Intelligent Optimization**: ECO_MODE, caching, and prescreening for cost efficiency

### 4. **Production Ready with Advanced Reliability**
- **Error Resilience**: Graceful degradation with comprehensive error categorization
- **Performance Optimized**: Intelligent caching, concurrent processing, early exit optimizations
- **Observable**: Detailed logging, performance metrics, and decision audit trails
- **Anti-Exploitation**: Sophisticated scoring caps and manipulation detection

## System Components

### **Entry Point Layer**
- **`forward.py`**: Main validator entry point, lifecycle management, and miner UID coordination
- **Responsibilities**: Validator startup, miner discovery, score synchronization, graceful shutdown

### **Reward Engine Core** (`reward_engine/`)

The sophisticated orchestration system that coordinates content evaluation and reward calculation:

```
RewardOrchestrator → MinerQueryService → PlatformEvaluatorRegistry → [Platform Evaluators]
                  ↓                                                            ↓
[Sequential Processing] ← ScoreAggregationService ← EmissionCalculationService ← [Results]
         ↓
RewardDistributionService → [Final Rewards & Stats]
```

#### **Orchestrator** (`orchestrator.py`)
- **Sequential Processing**: Just-in-time miner querying to prevent token expiration
- **Error Recovery**: Comprehensive error handling with fallback mechanisms
- **Global Ratio Management**: Updates cached views-to-revenue ratios for Non-YPP scoring
- **State Coordination**: Manages evaluation state and cleanup between cycles

#### **Service Layer** (`services/`)
- **`MinerQueryService`**: Bittensor protocol communication with retry logic and timeout handling
- **`ScoreAggregationService`**: Multi-platform score combination with normalization
- **`EmissionCalculationService`**: USD target calculation with scaling factor application
- **`RewardDistributionService`**: Final reward normalization with subnet treasury allocation
- **`PlatformRegistry`**: Platform evaluator management with priority-based selection

#### **Interface Layer** (`interfaces/`)
- **`PlatformEvaluator`**: Abstract interface for platform-specific evaluation with security requirements
- **`ScoreAggregator`**: Interface for different scoring strategies and aggregation methods
- **`EmissionCalculator`**: Interface for emission calculation methods with anti-exploitation support

#### **Data Models** (`models/`)
- **`EvaluationResult`**: Platform evaluation results with detailed decision tracking
- **`ScoreMatrix`**: Multi-dimensional scoring data with metadata and performance stats
- **`EmissionTarget`**: Emission calculation parameters with scaling factors
- **`MinerResponse`**: Structured miner response data with validation and error handling

#### **Exception Handling** (`exceptions/`)
- **`EvaluationError`**: Platform evaluation failures with context
- **`PlatformNotSupportedError`**: Unsupported platform detection
- **`InvalidTokenError`**: Authentication and credential failures
- **`ScoreCalculationError`**: Scoring calculation failures
- **`EmissionCalculationError`**: Emission calculation failures

### **Platform Layer** (`platforms/`)

Platform-specific content evaluation implementations with advanced capabilities:

#### **Current Platforms**
- **`youtube/`**: Comprehensive YouTube evaluation system with modular architecture
  - **Modular Video Evaluation**: Specialized validation, transcript, brief_matching, and orchestration components
  - **Enhanced Security**: Prompt injection detection and content manipulation prevention
  - **Performance Optimization**: Brief prescreening (60-80% LLM cost reduction) and ECO_MODE
  - **Dual Scoring System**: YPP/Non-YPP account support with anti-exploitation protection
  - **Advanced Analytics**: Comprehensive retention analysis and revenue-based scoring

#### **Platform Evaluation Flow**
```python
# Platform registry selects appropriate evaluator
evaluator = platform_registry.get_evaluator_for_response(response)
result = await evaluator.evaluate_accounts(response, briefs, metagraph_info)

# Enhanced YouTube evaluation pipeline:
1. OAuth credential validation
2. Channel data retrieval and qualification
3. Video discovery and batch data fetching
4. Multi-stage validation pipeline (privacy, retention, captions, security)
5. Brief prescreening and intelligent filtering
6. Concurrent LLM evaluation with priority selection
7. Dual scoring with anti-exploitation protection
8. Performance metrics and decision audit trails
```

### **Content Evaluation & Security Systems**

#### **LLM Router** (`clients/LLMRouter.py`)
- **Version-Based Routing**: Routes inference requests to appropriate LLM provider
  - **Versions 1-3**: OpenAI (GPT-4o with structured outputs)
  - **Versions 4+**: Chutes (DeepSeek-V3 for cost-effectiveness)
- **Prompt Injection**: Always uses Chutes for consistency and cost
- **Simple Interface**: Transparent routing - calling code unchanged

```python
# LLM routing based on prompt version
def evaluate_content_against_brief(brief, duration, description, transcript):
    prompt_version = brief.get('prompt_version', 1)
    if prompt_version >= 4:
        return ChuteClient.evaluate_content_against_brief(...)
    else:
        return OpenaiClient.evaluate_content_against_brief(...)
```

#### **Prompt Versioning System** (`clients/prompts.py`)
- **Multi-Version Support**: Registry-based prompt management (v3, v4+)
- **Version Selection**: Briefs specify `prompt_version` for evaluation approach
- **Enhanced Evaluation**: Different video type support per version
  - **V3**: Dedicated / Ad-read / Integrated / Other
  - **V4**: Advanced evaluation with improved structured format

```python
# Prompt version system
PROMPT_GENERATORS = {
    3: generate_brief_evaluation_prompt_v3,
    4: generate_brief_evaluation_prompt_v4,
}

def generate_brief_evaluation_prompt(brief, duration, description, transcript, version=3):
    prompt_generator = get_prompt_generator(version)
    return prompt_generator(brief, duration, description, transcript)
```

#### **Advanced Security: Prompt Injection Detection**
- **Token-Based Detection**: Unique token insertion to detect manipulation attempts
- **Content Auditing**: Systematic detection of evaluation influence attempts
- **Multi-Layer Validation**: Description and transcript security scanning
- **Automated Prevention**: Automatic rejection of manipulated content

#### **Brief Prescreening & Optimization**
- **Unique Identifier Filtering**: Pre-filter briefs before expensive LLM evaluation
- **Performance Impact**: 60-80% reduction in OpenAI API costs
- **Intelligent Processing**: Only eligible briefs proceed to content analysis
- **Cost Optimization**: Maintains evaluation accuracy while reducing expenses

### **Supporting Systems**

#### **Enhanced OpenAI Client** (`clients/OpenaiClient.py`)
- **Multi-Version Prompt Support**: Automatic version detection and routing
- **Intelligent Caching**: TTL-based caching with sliding expiration
- **Retry Logic**: Exponential backoff with comprehensive error handling
- **Security Integration**: Prompt injection detection and content safety
- **Performance Monitoring**: Request tracking and response time metrics

#### **Comprehensive Error Handling** (`utils/error_handling.py`)
- **Standardized Error Patterns**: Consistent error handling across all components
- **Context-Rich Logging**: Detailed error categorization with sanitized context
- **Graceful Degradation**: Safe fallbacks for component failures
- **Circuit Breaker Patterns**: Prevents cascade failures from external API issues

```python
# Error handling utilities
def log_and_raise_api_error(error, endpoint, params=None, context="API call")
def log_and_raise_validation_error(message, data=None, context="Data validation")
def log_and_raise_processing_error(error, operation, context=None)
def safe_operation(operation_name, default_return=None)  # Decorator
```

#### **Advanced Configuration Management** (`utils/config.py`)
- **Environment-Based**: Secure configuration with environment variable support
- **Feature Flags**: ECO_MODE, caching controls, security toggles
- **Performance Tuning**: Configurable thresholds, scaling factors, and optimization settings
- **Security Configuration**: API keys, authentication settings, and security parameters

#### **State Management & Monitoring** (`utils/state.py`, `utils/publish_stats.py`)
- **Global State Tracking**: API call counters, scored video tracking, performance metrics
- **Performance Publishing**: Real-time stats publication with retry logic
- **Resource Management**: Memory optimization and cleanup coordination
- **Observability**: Comprehensive performance and decision tracking

## Data Flow Architecture

### **1. Enhanced Forward Pass Initiation**
```python
async def forward(self):
    # Entry point with comprehensive error handling
    miner_uids = get_all_uids(self)
    orchestrator = get_reward_orchestrator()
    
    try:
        rewards, stats = await orchestrator.calculate_rewards(self, miner_uids)
        return rewards, stats
    except Exception as e:
        bt.logging.error(f"Forward pass failed: {e}")
        return fallback_rewards(miner_uids), []
```

### **2. Advanced Reward Calculation Workflow**
```python
# RewardOrchestrator coordinates sophisticated pipeline:
briefs = get_briefs()                                    # Content requirements
                                                        
# Sequential processing prevents token expiration
for uid in uids:
    miner_response = await miner_query.query_single_miner(validator_self, uid)
    result = await evaluate_single_miner(miner_response, briefs, metagraph)
    evaluation_results.add_result(uid, result)

# Advanced aggregation and optimization
score_matrix = score_aggregator.aggregate_scores(evaluation_results, briefs)
update_global_ratio(evaluation_results)                # Views-to-revenue ratio update
emission_targets = emission_calculator.calculate()      # USD target calculation
rewards, stats = reward_distributor.calculate()         # Final distribution
```

### **3. Multi-Stage Platform Evaluation Process**
```python
# Enhanced platform evaluation with security and optimization
evaluator = platform_registry.get_evaluator_for_response(response)
result = await evaluator.evaluate_accounts(response, briefs, metagraph_info)

# YouTube evaluation pipeline example:
1. OAuth credential validation with retry logic
2. Channel data retrieval and blacklist checking
3. Video discovery with configurable lookback
4. Batch data retrieval optimization
5. Multi-stage validation pipeline:
   - Privacy and accessibility checks
   - Publish date validation against brief windows
   - Retention analysis and threshold validation
   - Caption verification (auto-generated only)
6. Security auditing:
   - Transcript retrieval with error handling
   - Prompt injection detection
7. Intelligent brief evaluation:
   - Unique identifier prescreening
   - Concurrent LLM evaluation (max 5 workers)
   - Priority-based selection for single brief matching
8. Advanced scoring:
   - YPP/Non-YPP dual scoring system
   - Anti-exploitation median capping
   - Performance optimization and early exits
```

### **4. Enhanced Score Aggregation & Distribution**
```python
# Multi-platform score aggregation with comprehensive error handling
total_scores = aggregate_platform_scores(evaluation_results)

# Advanced emission calculation with anti-exploitation
emission_targets = calculate_emission_targets(scores, briefs)

# Final distribution with subnet treasury and error recovery
final_rewards = distribute_rewards(emission_targets, uids)
```

## Performance & Reliability

### **Performance Optimizations**
- **Brief Prescreening**: 60-80% reduction in LLM API costs through intelligent filtering
- **Concurrent Processing**: Parallel brief evaluation with configurable worker limits
- **ECO_MODE**: Early exit optimizations for failed validation checks
- **Intelligent Caching**: Multi-layer caching with TTL, sliding expiration, and size limits
- **Batch Operations**: Optimized API usage with batch data retrieval
- **Sequential Miner Processing**: Prevents OAuth token expiration through just-in-time processing

### **Advanced Reliability Features**
- **Graceful Degradation**: System continues with reduced functionality on component failures
- **Comprehensive Error Handling**: Standardized error categorization with detailed logging
- **Security Auditing**: Multi-layer prompt injection detection and content safety
- **Anti-Exploitation Protection**: Median-based scoring caps prevent fake engagement gaming
- **Fallback Mechanisms**: Safe reward distribution when evaluation components fail
- **Circuit Breaker Patterns**: Prevents cascade failures from external API issues

### **Enhanced Monitoring & Observability**
- **Structured Logging**: Context-rich logging with sanitized sensitive data
- **Performance Metrics**: Detailed API usage, timing, and optimization effectiveness tracking
- **Decision Audit Trails**: Complete evaluation decision tracking for compliance
- **Error Categorization**: Systematic error tracking with recovery action logging
- **Health Monitoring**: Component health checks and performance threshold monitoring
- **Cost Optimization Metrics**: Prescreening savings and optimization effectiveness

## Advanced Security Architecture

### **Multi-Layer Security System**
```python
# Content security pipeline
1. Input Validation: Sanitize and validate all inputs
2. Authentication: Secure OAuth credential handling
3. Prompt Injection Detection: Token-based manipulation detection
4. Content Auditing: Systematic evaluation influence detection
5. Output Sanitization: Clean and validate all outputs
```

### **Security Features**
- **Prompt Injection Prevention**: Advanced detection with unique token validation
- **Content Manipulation Detection**: Systematic auditing of evaluation influence attempts
- **Secure Credential Handling**: OAuth token management with expiration handling
- **Data Sanitization**: Comprehensive input/output cleaning and validation
- **Access Control**: Role-based access with comprehensive audit trails

## Testing Architecture

### **Comprehensive Test Categories**
```bash
# Complete test coverage across all layers and security aspects
python -m pytest tests/validator/reward_engine/models/        # Data model tests
python -m pytest tests/validator/reward_engine/services/      # Service layer tests  
python -m pytest tests/validator/reward_engine/integration/   # End-to-end tests
python -m pytest tests/validator/platforms/youtube/           # Platform-specific tests
python -m pytest tests/validator/security/                    # Security feature tests
python -m pytest tests/validator/performance/                 # Performance tests
```

### **Advanced Testing Strategies**
- **Unit Tests**: Individual component isolation with comprehensive mocking
- **Integration Tests**: Cross-component workflow validation with error injection
- **Performance Tests**: Execution time, resource usage, and optimization validation
- **Security Tests**: Prompt injection detection and content manipulation testing
- **Mock-Heavy Testing**: External API calls fully mocked for reliability and speed
- **Error Handling Tests**: Comprehensive error scenario validation

## Migration & Compatibility

### **Backward Compatibility Guarantees**
The enhanced architecture maintains complete compatibility with existing systems:
- **Same Interface**: Identical return formats for `(rewards, stats_list)`
- **Same Configuration**: All existing config variables continue to work with enhancements
- **Same Functionality**: All existing evaluation logic preserved with optimizations
- **Additive Changes**: New features are additive and don't break existing workflows

### **Migration Benefits**
- **Performance**: 60-80% reduction in LLM costs through intelligent prescreening
- **Security**: Advanced prompt injection detection and content manipulation prevention
- **Reliability**: Comprehensive error handling with graceful degradation
- **Observability**: Detailed performance metrics and decision audit trails
- **Maintainability**: Modular architecture with standardized error handling patterns

## Future Roadmap

### **Platform Expansion**
The modular architecture supports seamless addition of new social media platforms:
- **TikTok Platform**: Video evaluation with platform-specific metrics
- **Twitter/X Platform**: Post and engagement evaluation
- **Instagram Platform**: Visual content and story evaluation
- **Generic Platform Interface**: Standardized evaluation patterns for rapid platform addition

### **Advanced Features**
- **Real-time Evaluation**: Streaming evaluation for live content
- **Machine Learning Integration**: AI-powered content scoring and manipulation detection
- **Multi-Modal Analysis**: Combined video, audio, text, and visual evaluation
- **Advanced Analytics**: Predictive modeling and trend analysis
- **Enhanced Performance**: Continued optimization for speed, cost, and reliability

### **Security Enhancements**
- **Advanced Threat Detection**: ML-based manipulation detection
- **Zero-Trust Architecture**: Comprehensive security validation at every layer
- **Audit Compliance**: Enhanced logging and compliance reporting
- **Automated Response**: Self-healing security incident response

The Bitcast Validator represents a mature, production-ready system with sophisticated evaluation capabilities, advanced security features, comprehensive performance optimizations, and intelligent cost management while maintaining full backward compatibility and extensibility for future platform additions. 