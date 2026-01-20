# τ²-Bench Architecture Design Document

---

## 1. Executive Summary

**System Purpose:** τ²-Bench is a Python benchmark framework for evaluating conversational customer service agents in dual-control environments, simulating interactions between an AI agent, a user simulator, and a domain environment across multiple domains (airline, retail, telecom).

**Key Features:**

- Multi-domain evaluation (airline, retail, telecom)
- LLM-based user simulation for realistic customer behavior
- Comprehensive evaluation across actions, communication, and environment outcomes
- Gymnasium-compatible interface for reinforcement learning
- Flexible agent and domain registry system

---

## 2. System Context

### 2.1 High-Level Overview

```mermaid
graph TB
    subgraph "External"
        LLM[☁️ LLM Providers<br/>OpenAI, Anthropic, etc.]
    end

    subgraph "τ²-Bench Core"
        CLI[🖥️ CLI Interface]
        Orchestrator[⚙️ Orchestrator]
        Agent[🤖 Agent]
        User[👤 User Simulator]
        Env[🌐 Environment]
        Eval[📊 Evaluator]
    end

    subgraph "Domains"
        Airline[✈️ Airline]
        Retail[🛒 Retail]
        Telecom[📱 Telecom]
    end

    subgraph "Data"
        Tasks[(📋 Tasks)]
        DB[(💾 Domain DB)]
        Results[(📈 Results)]
    end

    CLI --> Orchestrator
    Orchestrator --> Agent
    Orchestrator --> User
    Orchestrator --> Env
    Agent --> LLM
    User --> LLM
    Env --> Airline
    Env --> Retail
    Env --> Telecom
    Airline --> DB
    Retail --> DB
    Telecom --> DB
    Orchestrator --> Eval
    Eval --> Results

    classDef external fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef core fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef domain fill:#FFE4B5,stroke:#333,stroke-width:2px,color:black
    classDef data fill:#87CEEB,stroke:#333,stroke-width:2px,color:darkblue

    class LLM external
    class CLI,Orchestrator,Agent,User,Env,Eval core
    class Airline,Retail,Telecom domain
    class Tasks,DB,Results data
```

---

## 3. Core Components Architecture

### 3.1 Component Overview

```mermaid
graph TB
    subgraph "CLI Layer"
        Run[tau2 run]
        Play[tau2 play]
        View[tau2 view]
        Submit[tau2 submit]
        Domain[tau2 domain]
    end

    subgraph "Orchestration Layer"
        Orch[⚙️ Orchestrator<br/>Message Router]
    end

    subgraph "Actor Layer"
        BaseAgent[🤖 BaseAgent]
        LLMAgent[LLMAgent]
        LLMSoloAgent[LLMSoloAgent]
        LLMGTAgent[LLMGTAgent]
        UserSim[👤 UserSimulator]
        DummyUser[DummyUser]
    end

    subgraph "Environment Layer"
        EnvCore[🌐 Environment]
        Toolkit[🔧 ToolKit]
        Tools[Agent Tools]
        UserTools[User Tools]
    end

    subgraph "Evaluation Layer"
        EvalCore[📊 Evaluator]
        ActionEval[ActionEvaluator]
        CommEval[CommunicateEvaluator]
        EnvEval[EnvironmentEvaluator]
    end

    subgraph "Domain Layer"
        MockDomain[Mock]
        AirlineDomain[Airline]
        RetailDomain[Retail]
        TelecomDomain[Telecom]
    end

    Run --> Orch
    Play --> Orch

    Orch --> BaseAgent
    Orch --> UserSim
    Orch --> EnvCore

    BaseAgent --> LLMAgent
    BaseAgent --> LLMSoloAgent
    BaseAgent --> LLMGTAgent

    UserSim --> DummyUser

    EnvCore --> Toolkit
    Toolkit --> Tools
    Toolkit --> UserTools

    EnvCore --> MockDomain
    EnvCore --> AirlineDomain
    EnvCore --> RetailDomain
    EnvCore --> TelecomDomain

    Orch --> EvalCore
    EvalCore --> ActionEval
    EvalCore --> CommEval
    EvalCore --> EnvEval

    classDef cli fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef orch fill:#FFD700,stroke:#333,stroke-width:2px,color:black
    classDef actor fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef env fill:#87CEEB,stroke:#333,stroke-width:2px,color:darkblue
    classDef eval fill:#FFB6C1,stroke:#333,stroke-width:2px,color:black
    classDef domain fill:#FFE4B5,stroke:#333,stroke-width:2px,color:black

    class Run,Play,View,Submit,Domain cli
    class Orch orch
    class BaseAgent,LLMAgent,LLMSoloAgent,LLMGTAgent,UserSim,DummyUser actor
    class EnvCore,Toolkit,Tools,UserTools env
    class EvalCore,ActionEval,CommEval,EnvEval eval
    class MockDomain,AirlineDomain,RetailDomain,TelecomDomain domain
```

---

## 4. Key Workflows

### 4.1 Main Simulation Loop

The Orchestrator manages the turn-based communication protocol between Agent, User, and Environment.

```mermaid
flowchart TD
    Start([🚀 Start Simulation]) --> Init[📋 Initialize from Task]
    Init --> LoadState[💾 Load Initial State]
    LoadState --> SetHistory[📝 Set Message History]
    SetHistory --> Loop{🔄 Step Loop}

    Loop --> CheckDone{✓ Done?}
    CheckDone -->|No| Route[📨 Route Message]
    CheckDone -->|Yes| Terminate[🏁 Terminate]

    Route --> GetSender{📤 From Role?}
    GetSender -->|Agent| AgentGen[🤖 Agent Generate]
    GetSender -->|User| UserGen[👤 User Generate]
    GetSender -->|Env| EnvResp[🌐 Env Response]

    AgentGen --> ProcessMsg[⚙️ Process Message]
    UserGen --> ProcessMsg
    EnvResp --> ProcessMsg

    ProcessMsg --> UpdateState[📝 Update State]
    UpdateState --> CheckTermination{⛔ Termination?}

    CheckTermination -->|Agent Stop| Terminate
    CheckTermination -->|User Stop| Terminate
    CheckTermination -->|Max Steps| Terminate
    CheckTermination -->|Max Errors| Terminate
    CheckTermination -->|None| Loop

    Terminate --> Evaluate[📊 Evaluate]
    Evaluate --> SaveResults[💾 Save Results]
    SaveResults --> End([✅ Complete])

    classDef startEnd fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef process fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef decision fill:#FFD700,stroke:#333,stroke-width:2px,color:black
    classDef action fill:#87CEEB,stroke:#333,stroke-width:2px,color:darkblue

    class Start,End startEnd
    class Init,LoadState,SetHistory,Route,AgentGen,UserGen,EnvResp,ProcessMsg,UpdateState,Evaluate,SaveResults,Terminate process
    class Loop,CheckDone,GetSender,CheckTermination decision
```

### 4.2 Message Flow Protocol

```mermaid
sequenceDiagram
    participant CLI as 🖥️ CLI
    participant Orch as ⚙️ Orchestrator
    participant Agent as 🤖 Agent
    participant User as 👤 User Simulator
    participant Env as 🌐 Environment

    Note over CLI,Env: Simulation Initialization
    CLI->>+Orch: run_simulation(task)
    Orch->>Orch: Initialize states

    Note over CLI,Env: Main Simulation Loop

    loop Until termination
        alt Agent's turn
            Orch->>+Agent: generate_next_message(user_msg)
            Agent->>Agent: Call LLM
            Agent-->>-Orch: AssistantMessage

            alt Has tool calls
                Orch->>+Env: get_response(tool_calls)
                Env->>Env: Execute tools
                Env-->>-Orch: ToolMessage(s)
                Orch->>Agent: Forward tool results
            else Has text content
                Orch->>User: Forward to user
            end

        else User's turn
            Orch->>+User: generate_next_message(agent_msg)
            User->>User: Call LLM
            User-->>-Orch: UserMessage

            alt Has user tool calls
                Orch->>+Env: get_response(user_tool_calls)
                Env-->>-Orch: ToolMessage(s)
                Orch->>User: Forward tool results
            else Has text content
                Orch->>Agent: Forward to agent
            end
        end
    end

    Note over CLI,Env: Termination & Evaluation
    Orch->>Orch: Evaluate trajectory
    Orch-->>-CLI: SimulationRun result
```

### 4.3 Agent Message Processing

```mermaid
flowchart TD
    Start([📥 Receive Message]) --> AddHistory[📝 Add to History]
    AddHistory --> CallLLM[☁️ Call LLM]
    CallLLM --> ParseResponse[🔍 Parse Response]

    ParseResponse --> CheckType{📋 Response Type?}

    CheckType -->|Tool Calls| CreateToolMsg[🔧 Create ToolCall Message]
    CheckType -->|Text| CreateTextMsg[💬 Create Text Message]
    CheckType -->|Stop Signal| CreateStop[🛑 Create Stop Message]

    CreateToolMsg --> ValidateTools[✓ Validate Tool Calls]
    ValidateTools --> ReturnMsg[📤 Return AssistantMessage]

    CreateTextMsg --> ReturnMsg
    CreateStop --> ReturnMsg

    ReturnMsg --> End([✅ Message Ready])

    classDef startEnd fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef process fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef decision fill:#FFD700,stroke:#333,stroke-width:2px,color:black

    class Start,End startEnd
    class AddHistory,CallLLM,ParseResponse,CreateToolMsg,CreateTextMsg,CreateStop,ValidateTools,ReturnMsg process
    class CheckType decision
```

### 4.4 Tool Execution Flow

```mermaid
sequenceDiagram
    participant Agent as 🤖 Agent
    participant Orch as ⚙️ Orchestrator
    participant Env as 🌐 Environment
    participant Toolkit as 🔧 ToolKit
    participant DB as 💾 Domain DB

    Agent->>Orch: AssistantMessage with ToolCalls

    loop For each ToolCall
        Orch->>+Env: get_response(tool_call)
        Env->>Env: Extract tool_name, arguments

        alt Agent tool
            Env->>+Toolkit: use_tool(name, args)
        else User tool
            Env->>+Toolkit: use_user_tool(name, args)
        end

        Toolkit->>Toolkit: Find tool method
        Toolkit->>+DB: Execute operation
        DB-->>-Toolkit: Result
        Toolkit-->>-Env: Tool result or error

        Env->>Env: Create ToolMessage
        Env-->>-Orch: ToolMessage
    end

    Orch->>Orch: Bundle into MultiToolMessage
    Orch->>Agent: Forward tool responses
```

### 4.5 User Simulator Flow

```mermaid
flowchart TD
    Start([📥 Receive Agent Message]) --> BuildPrompt[📝 Build System Prompt]
    BuildPrompt --> AddScenario[👤 Add User Scenario]
    AddScenario --> AddInstructions[📋 Add Task Instructions]

    AddInstructions --> CallLLM[☁️ Call LLM as User]
    CallLLM --> ParseResponse[🔍 Parse Response]

    ParseResponse --> CheckStop{🛑 Stop Keywords?}

    CheckStop -->|###STOP###| StopSignal[⏹️ User Stop]
    CheckStop -->|###TRANSFER###| TransferSignal[📞 Transfer]
    CheckStop -->|###OUT-OF-SCOPE###| OOSSignal[❌ Out of Scope]
    CheckStop -->|None| FlipRole[🔄 Flip Role to User]

    FlipRole --> CheckToolCalls{🔧 Has Tool Calls?}
    CheckToolCalls -->|Yes| FlipToolCalls[🔄 Flip Tool Requestor]
    CheckToolCalls -->|No| CreateUserMsg[💬 Create UserMessage]

    FlipToolCalls --> CreateUserMsg
    StopSignal --> CreateUserMsg
    TransferSignal --> CreateUserMsg
    OOSSignal --> CreateUserMsg

    CreateUserMsg --> End([📤 Return UserMessage])

    classDef startEnd fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef process fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef decision fill:#FFD700,stroke:#333,stroke-width:2px,color:black

    class Start,End startEnd
    class BuildPrompt,AddScenario,AddInstructions,CallLLM,ParseResponse,StopSignal,TransferSignal,OOSSignal,FlipRole,FlipToolCalls,CreateUserMsg process
    class CheckStop,CheckToolCalls decision
```

---

## 5. Evaluation System

### 5.1 Evaluation Pipeline

```mermaid
flowchart TD
    Start([📊 Start Evaluation]) --> GetTrajectory[📜 Get Message Trajectory]
    GetTrajectory --> CheckTermination{⛔ Valid Termination?}

    CheckTermination -->|Agent/User Stop| SelectEvaluators[📋 Select Evaluators]
    CheckTermination -->|Premature| ZeroReward[❌ Zero Reward]

    SelectEvaluators --> CheckBasis{📐 Reward Basis?}

    CheckBasis -->|ALL| RunAll[Run All Evaluators]
    CheckBasis -->|ENV| RunEnv[Run EnvironmentEvaluator]
    CheckBasis -->|ACTION| RunAction[Run ActionEvaluator]
    CheckBasis -->|COMMUNICATE| RunComm[Run CommunicateEvaluator]

    RunAll --> ActionEval[🎯 ActionEvaluator]
    RunAll --> CommEval[💬 CommunicateEvaluator]
    RunAll --> EnvEval[🌐 EnvironmentEvaluator]

    RunEnv --> EnvEval
    RunAction --> ActionEval
    RunComm --> CommEval

    ActionEval --> CheckActions[✓ Check Expected Actions]
    CommEval --> CheckComms[✓ Check Required Info]
    EnvEval --> CheckEnvState[✓ Check Environment State]

    CheckActions --> Aggregate[📈 Aggregate Rewards]
    CheckComms --> Aggregate
    CheckEnvState --> Aggregate

    ZeroReward --> FinalResult[📊 Final Result]
    Aggregate --> FinalResult
    FinalResult --> End([✅ Evaluation Complete])

    classDef startEnd fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef process fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef decision fill:#FFD700,stroke:#333,stroke-width:2px,color:black
    classDef evaluator fill:#87CEEB,stroke:#333,stroke-width:2px,color:darkblue
    classDef error fill:#FFB6C1,stroke:#333,stroke-width:2px,color:black

    class Start,End startEnd
    class GetTrajectory,SelectEvaluators,RunAll,RunEnv,RunAction,RunComm,CheckActions,CheckComms,CheckEnvState,Aggregate,FinalResult process
    class CheckTermination,CheckBasis decision
    class ActionEval,CommEval,EnvEval evaluator
    class ZeroReward error
```

### 5.2 Evaluator Details

```mermaid
graph TB
    subgraph "ActionEvaluator"
        AE_Input[📜 Message Trajectory]
        AE_Extract[🔍 Extract Tool Calls]
        AE_Compare[⚖️ Compare with Expected Actions]
        AE_ArgMatch[🔧 Check Argument Matching]
        AE_Result[📊 Reward: 0.0 or 1.0]

        AE_Input --> AE_Extract
        AE_Extract --> AE_Compare
        AE_Compare --> AE_ArgMatch
        AE_ArgMatch --> AE_Result
    end

    subgraph "CommunicateEvaluator"
        CE_Input[📜 Message Trajectory]
        CE_Extract[💬 Extract Text Content]
        CE_Search[🔍 Search for Required Info]
        CE_Result[📊 Reward based on matches]

        CE_Input --> CE_Extract
        CE_Extract --> CE_Search
        CE_Search --> CE_Result
    end

    subgraph "EnvironmentEvaluator"
        EE_Input[📜 Message Trajectory]
        EE_Reconstruct[🔄 Reconstruct Environment]
        EE_RunAssertions[✓ Run env_assertions]
        EE_CheckDB[💾 Check DB State]
        EE_Result[📊 Combined Reward]

        EE_Input --> EE_Reconstruct
        EE_Reconstruct --> EE_RunAssertions
        EE_RunAssertions --> EE_CheckDB
        EE_CheckDB --> EE_Result
    end

    classDef input fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef process fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef result fill:#FFD700,stroke:#333,stroke-width:2px,color:black

    class AE_Input,CE_Input,EE_Input input
    class AE_Extract,AE_Compare,AE_ArgMatch,CE_Extract,CE_Search,EE_Reconstruct,EE_RunAssertions,EE_CheckDB process
    class AE_Result,CE_Result,EE_Result result
```

---

## 6. Domain Structure

### 6.1 Domain Architecture

```mermaid
graph TB
    subgraph "Domain Interface"
        GetEnv[get_environment]
        GetTasks[get_tasks]
    end

    subgraph "Domain Components"
        DataModel[📋 data_model.py<br/>Domain data classes]
        Tools[🔧 tools.py<br/>Agent ToolKit]
        UserTools[👤 user_tools.py<br/>User ToolKit]
        EnvSetup[🌐 environment.py<br/>Environment factory]
        Utils[🛠️ utils.py<br/>Constants & helpers]
    end

    subgraph "Domain Data"
        TasksJSON[📋 tasks.json<br/>Task definitions]
        SplitTasks[📊 split_tasks.json<br/>Train/test/base splits]
        Policy[📜 policy.md<br/>Agent guidelines]
        Database[💾 db.json/db.toml<br/>Domain database]
    end

    GetEnv --> EnvSetup
    GetTasks --> TasksJSON
    EnvSetup --> Tools
    EnvSetup --> UserTools
    EnvSetup --> DataModel
    Tools --> Utils
    UserTools --> Utils
    TasksJSON --> SplitTasks
    EnvSetup --> Database
    EnvSetup --> Policy

    classDef interface fill:#FFD700,stroke:#333,stroke-width:2px,color:black
    classDef component fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef data fill:#87CEEB,stroke:#333,stroke-width:2px,color:darkblue

    class GetEnv,GetTasks interface
    class DataModel,Tools,UserTools,EnvSetup,Utils component
    class TasksJSON,SplitTasks,Policy,Database data
```

### 6.2 Toolkit Pattern

```mermaid
flowchart TD
    Start([🔧 Define Tool]) --> Decorator["@is_tool decorator"]
    Decorator --> MarkMethod[Mark method as tool]
    MarkMethod --> SetType[Set tool type:<br/>READ/WRITE/THINK/GENERIC]

    SetType --> Discovery[🔍 Auto-Discovery]
    Discovery --> CollectTools[Collect all @is_tool methods]
    CollectTools --> ConvertSchema[Convert to Tool objects]
    ConvertSchema --> RegisterTools[Register in ToolKit]

    RegisterTools --> Ready([✅ Tools Ready])

    subgraph "Tool Execution"
        Call([📞 Tool Call]) --> FindTool[Find tool by name]
        FindTool --> MapArgs[Map arguments to params]
        MapArgs --> Execute[Execute method]
        Execute --> ReturnResult[Return result]
    end

    Ready --> Call

    classDef startEnd fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef process fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef exec fill:#FFE4B5,stroke:#333,stroke-width:2px,color:black

    class Start,Ready,Call startEnd
    class Decorator,MarkMethod,SetType,Discovery,CollectTools,ConvertSchema,RegisterTools process
    class FindTool,MapArgs,Execute,ReturnResult exec
```

---

## 7. Agent Execution Modes

### 7.1 Execution Mode Comparison

```mermaid
graph LR
    subgraph "Standard Mode"
        S_Agent[🤖 LLMAgent]
        S_User[👤 UserSimulator]
        S_Env[🌐 Environment]

        S_Agent <-->|Conversation| S_User
        S_Agent <-->|Tool Calls| S_Env
        S_User <-->|User Tools| S_Env
    end

    subgraph "Solo Mode"
        Solo_Agent[🤖 LLMSoloAgent]
        Solo_Dummy[⬜ DummyUser]
        Solo_Env[🌐 Environment]

        Solo_Agent -->|Tool Calls Only| Solo_Env
        Solo_Agent -.->|No Interaction| Solo_Dummy
    end

    subgraph "GT Mode"
        GT_Agent[🤖 LLMGTAgent]
        GT_User[👤 UserSimulator]
        GT_Env[🌐 Environment]

        GT_Agent <-->|Guided by Expected Actions| GT_User
        GT_Agent <-->|Tool Calls| GT_Env
    end

    classDef agent fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef user fill:#87CEEB,stroke:#333,stroke-width:2px,color:darkblue
    classDef env fill:#FFE4B5,stroke:#333,stroke-width:2px,color:black
    classDef dummy fill:#E0E0E0,stroke:#333,stroke-width:2px,color:gray

    class S_Agent,Solo_Agent,GT_Agent agent
    class S_User,GT_User user
    class S_Env,Solo_Env,GT_Env env
    class Solo_Dummy dummy
```

### 7.2 Solo Mode Workflow

```mermaid
sequenceDiagram
    participant CLI as 🖥️ CLI
    participant Orch as ⚙️ Orchestrator
    participant Agent as 🤖 LLMSoloAgent
    participant Env as 🌐 Environment

    CLI->>+Orch: run_simulation(task, solo_mode=True)
    Orch->>Agent: Initialize with ticket in system prompt
    Note over Agent: System prompt contains:<br/>- Domain policy<br/>- Task ticket description<br/>- Special "done" tool

    loop Until done
        Orch->>+Agent: generate_next_message()
        Agent->>Agent: Generate tool calls only

        alt Regular tool calls
            Agent-->>-Orch: AssistantMessage(tool_calls)
            Orch->>+Env: Execute tools
            Env-->>-Orch: ToolMessage(s)
            Orch->>Agent: Forward results

        else "done" tool call
            Agent-->>Orch: AssistantMessage(done tool)
            Orch->>Orch: Mark as STOP
        end
    end

    Orch->>Orch: Evaluate
    Orch-->>-CLI: SimulationRun result
```

---

## 8. Data Models

### 8.1 Message Type Hierarchy

```mermaid
classDiagram
    class Message {
        <<abstract>>
        +role: str
        +content: str | None
        +tool_calls: List[ToolCall] | None
    }

    class SystemMessage {
        +role = "system"
        +content: str
    }

    class UserMessage {
        +role = "user"
        +content: str | None
        +tool_calls: List[ToolCall] | None
    }

    class AssistantMessage {
        +role = "assistant"
        +content: str | None
        +tool_calls: List[ToolCall] | None
    }

    class ToolMessage {
        +role = "tool"
        +content: str
        +error: str | None
        +requestor: str
        +tool_call_id: str
    }

    class MultiToolMessage {
        +messages: List[ToolMessage]
    }

    class ToolCall {
        +id: str
        +name: str
        +arguments: dict
        +requestor: str
    }

    Message <|-- SystemMessage
    Message <|-- UserMessage
    Message <|-- AssistantMessage
    Message <|-- ToolMessage
    Message <|-- MultiToolMessage

    UserMessage --> ToolCall
    AssistantMessage --> ToolCall
    MultiToolMessage --> ToolMessage
```

### 8.2 Task Data Model

```mermaid
classDiagram
    class Task {
        +id: str
        +user_scenario: UserScenario
        +ticket: str | None
        +initial_state: InitialState | None
        +evaluation_criteria: EvaluationCriteria
        +description: TaskDescription | None
    }

    class UserScenario {
        +user_instructions: UserInstructions
        +known_info: dict
        +unknown_info: dict
    }

    class UserInstructions {
        +domain: str
        +reason_for_call: str
        +known_info: str
        +unknown_info: str
        +task_instructions: str
    }

    class InitialState {
        +initialization_data: dict
        +initialization_actions: List[Action]
        +message_history: List[Message]
    }

    class EvaluationCriteria {
        +actions: List[Action]
        +communicate_info: List[str]
        +env_assertions: str | None
        +reward_basis: RewardBasis
    }

    class Action {
        +action_id: str
        +requestor: str
        +name: str
        +arguments: dict
        +compare_args: List[str] | None
        +info: str | None
    }

    Task --> UserScenario
    Task --> InitialState
    Task --> EvaluationCriteria
    UserScenario --> UserInstructions
    InitialState --> Action
    EvaluationCriteria --> Action
```

---

## 9. Registry System

### 9.1 Registration Flow

```mermaid
flowchart TD
    Start([🚀 Application Start]) --> RegisterDomains[📦 Register Domains]
    RegisterDomains --> RegisterAgents[🤖 Register Agents]
    RegisterAgents --> RegisterUsers[👤 Register Users]
    RegisterUsers --> RegisterTasks[📋 Register Task Loaders]
    RegisterTasks --> Ready([✅ Registry Ready])

    subgraph "Domain Registration"
        D1[register_domain<br/>mock, get_mock_env]
        D2[register_domain<br/>airline, get_airline_env]
        D3[register_domain<br/>retail, get_retail_env]
        D4[register_domain<br/>telecom, get_telecom_env]
    end

    subgraph "Agent Registration"
        A1[register_agent<br/>LLMAgent, llm_agent]
        A2[register_agent<br/>LLMSoloAgent, llm_agent_solo]
        A3[register_agent<br/>LLMGTAgent, llm_agent_gt]
    end

    subgraph "User Registration"
        U1[register_user<br/>UserSimulator, llm_user]
        U2[register_user<br/>DummyUser, dummy_user]
    end

    RegisterDomains --> D1
    RegisterDomains --> D2
    RegisterDomains --> D3
    RegisterDomains --> D4

    RegisterAgents --> A1
    RegisterAgents --> A2
    RegisterAgents --> A3

    RegisterUsers --> U1
    RegisterUsers --> U2

    classDef startEnd fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef process fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef reg fill:#FFE4B5,stroke:#333,stroke-width:2px,color:black

    class Start,Ready startEnd
    class RegisterDomains,RegisterAgents,RegisterUsers,RegisterTasks process
    class D1,D2,D3,D4,A1,A2,A3,U1,U2 reg
```

---

## 10. Gymnasium Integration

### 10.1 Gym Agent Interface

```mermaid
sequenceDiagram
    participant RL as 🤖 RL Algorithm
    participant GymEnv as 🎮 GymAgent
    participant Orch as ⚙️ Orchestrator
    participant Agent as 🤖 Agent
    participant User as 👤 User

    RL->>+GymEnv: reset()
    GymEnv->>+Orch: Initialize simulation
    Orch-->>-GymEnv: Initial state
    GymEnv-->>-RL: observation, info

    loop Training Episode
        RL->>+GymEnv: step(action)
        GymEnv->>+Orch: Apply action

        alt Agent mode
            Orch->>+Agent: generate_next_message(action)
            Agent-->>-Orch: Response
        else User mode
            Orch->>+User: generate_next_message(action)
            User-->>-Orch: Response
        end

        Orch-->>-GymEnv: New state
        GymEnv->>GymEnv: Calculate reward
        GymEnv-->>-RL: observation, reward, terminated, truncated, info
    end

    RL->>GymEnv: close()
```

---

## 11. CLI Commands

### 11.1 Command Flow

```mermaid
flowchart TD
    subgraph "tau2 run"
        Run_Parse[Parse CLI args]
        Run_Load[Load domain & tasks]
        Run_Init[Initialize agent/user]
        Run_Sim[Run simulations]
        Run_Eval[Evaluate results]
        Run_Save[Save to JSON]

        Run_Parse --> Run_Load --> Run_Init --> Run_Sim --> Run_Eval --> Run_Save
    end

    subgraph "tau2 play"
        Play_Parse[Parse CLI args]
        Play_Load[Load domain]
        Play_Interactive[Interactive session]

        Play_Parse --> Play_Load --> Play_Interactive
    end

    subgraph "tau2 view"
        View_Parse[Parse CLI args]
        View_Load[Load results]
        View_Display[Display metrics]

        View_Parse --> View_Load --> View_Display
    end

    subgraph "tau2 submit"
        Sub_Prepare[Prepare submission]
        Sub_Validate[Validate format]
        Sub_Package[Package results]

        Sub_Prepare --> Sub_Validate --> Sub_Package
    end

    subgraph "tau2 domain"
        Dom_Parse[Parse domain name]
        Dom_Start[Start FastAPI server]
        Dom_Docs[Serve API docs]

        Dom_Parse --> Dom_Start --> Dom_Docs
    end

    classDef step fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen

    class Run_Parse,Run_Load,Run_Init,Run_Sim,Run_Eval,Run_Save step
    class Play_Parse,Play_Load,Play_Interactive step
    class View_Parse,View_Load,View_Display step
    class Sub_Prepare,Sub_Validate,Sub_Package step
    class Dom_Parse,Dom_Start,Dom_Docs step
```

---

## 12. Configuration & Settings

### 12.1 Configuration Hierarchy

```mermaid
graph TB
    subgraph "Configuration Sources"
        Defaults[⚙️ config.py Defaults]
        EnvVars[🌍 Environment Variables]
        DotEnv[📄 .env File]
        CLI[🖥️ CLI Arguments]
    end

    subgraph "Key Settings"
        MaxSteps[MAX_STEPS = 200]
        MaxConcurrency[MAX_CONCURRENCY = 3]
        CacheEnabled[LLM_CACHE_ENABLED = False]
        LiteLLM[LiteLLM Provider Config]
    end

    subgraph "LLM Configuration"
        APIKeys[API Keys]
        ModelIDs[Model IDs]
        Parameters[Temperature, etc.]
    end

    Defaults --> MaxSteps
    Defaults --> MaxConcurrency
    Defaults --> CacheEnabled

    EnvVars --> APIKeys
    DotEnv --> APIKeys
    CLI --> ModelIDs
    CLI --> Parameters

    APIKeys --> LiteLLM
    ModelIDs --> LiteLLM
    Parameters --> LiteLLM

    classDef source fill:#E6E6FA,stroke:#333,stroke-width:2px,color:darkblue
    classDef setting fill:#90EE90,stroke:#333,stroke-width:2px,color:darkgreen
    classDef llm fill:#FFE4B5,stroke:#333,stroke-width:2px,color:black

    class Defaults,EnvVars,DotEnv,CLI source
    class MaxSteps,MaxConcurrency,CacheEnabled,LiteLLM setting
    class APIKeys,ModelIDs,Parameters llm
```

---

## 13. End-to-End Simulation Flow

### 13.1 Complete Execution Sequence

```mermaid
sequenceDiagram
    actor Developer as 👨‍💻 Developer
    participant CLI as 🖥️ CLI
    participant Registry as 📦 Registry
    participant Orch as ⚙️ Orchestrator
    participant Agent as 🤖 Agent
    participant User as 👤 User Simulator
    participant Env as 🌐 Environment
    participant LLM as ☁️ LLM Provider
    participant Eval as 📊 Evaluator
    participant FS as 💾 File System

    Developer->>+CLI: tau2 run --domain airline --agent-llm gpt-4.1

    Note over CLI,FS: Initialization Phase
    CLI->>+Registry: get_domain("airline")
    Registry-->>-CLI: Environment factory
    CLI->>+Registry: get_agent("llm_agent")
    Registry-->>-CLI: Agent class
    CLI->>+Registry: get_user("llm_user")
    Registry-->>-CLI: User class
    CLI->>+Registry: get_tasks("airline")
    Registry-->>-CLI: Task list

    Note over CLI,FS: Simulation Phase (per task)
    loop For each task
        CLI->>+Orch: create_simulation(task, agent, user, env)
        Orch->>Env: Initialize environment state
        Orch->>Agent: Set system prompt with policy
        Orch->>User: Set scenario instructions

        loop Simulation steps
            alt Agent turn
                Orch->>+Agent: generate_next_message()
                Agent->>+LLM: Chat completion request
                LLM-->>-Agent: Response
                Agent-->>-Orch: AssistantMessage

                opt Tool calls present
                    Orch->>+Env: Execute tool calls
                    Env-->>-Orch: Tool results
                end

            else User turn
                Orch->>+User: generate_next_message()
                User->>+LLM: Chat completion request
                LLM-->>-User: Response
                User-->>-Orch: UserMessage
            end
        end

        Note over CLI,FS: Evaluation Phase
        Orch->>+Eval: evaluate(trajectory, criteria)
        Eval->>Eval: Run ActionEvaluator
        Eval->>Eval: Run CommunicateEvaluator
        Eval->>Eval: Run EnvironmentEvaluator
        Eval-->>-Orch: Rewards & metrics

        Orch-->>-CLI: SimulationRun result
    end

    Note over CLI,FS: Output Phase
    CLI->>+FS: Save results JSON
    FS-->>-CLI: Saved
    CLI-->>-Developer: Display summary metrics
```

---

## 14. Summary

τ²-Bench provides a comprehensive framework for evaluating conversational AI agents in customer service scenarios. Key architectural highlights:

| Component          | Purpose                 | Key Features                                   |
|--------------------|-------------------------|------------------------------------------------|
| **Orchestrator**   | Message routing         | Turn-based protocol, termination handling      |
| **Agent**          | Response generation     | LLM-powered, multiple modes (standard/solo/GT) |
| **User Simulator** | Customer simulation     | Scenario-driven, LLM-based responses           |
| **Environment**    | Domain state & tools    | Toolkit pattern, dual tool sets                |
| **Evaluator**      | Performance measurement | Action, communication, environment checks      |
| **Registry**       | Component discovery     | Flexible agent/domain registration             |
| **Gym Interface**  | RL integration          | Gymnasium-compatible API                       |

The modular design enables easy extension with new domains, agents, and evaluation criteria while maintaining consistent simulation semantics.

---

**Related Files:**

- [src/tau2/orchestrator/](../src/tau2/orchestrator/) - Orchestrator implementation
- [src/tau2/agent/](../src/tau2/agent/) - Agent implementations
- [src/tau2/domains/](../src/tau2/domains/) - Domain implementations
- [data/tau2/domains/](../data/tau2/domains/) - Domain data files
