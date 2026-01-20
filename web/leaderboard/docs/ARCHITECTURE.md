# tau2-bench Leaderboard UI - Architecture Design Document

**Author:** tau2-bench Team
**Date:** 2025-01-20
**Status:** Approved
**Version:** 1.0

---

## 1. Executive Summary

The tau2-bench Leaderboard UI is a lightweight, static React application for displaying and exploring benchmark results from the tau2-bench evaluation framework. It provides interactive visualization of model performance metrics, trajectory exploration, and task analysis across multiple domains (airline, retail, telecom).

**Business Context:**

- Display benchmark results for conversational customer service agents
- Enable researchers to compare model performance across domains
- Provide transparency into evaluation trajectories and task definitions
- Support community contributions via leaderboard submissions

**Key Decisions:**

- Static-first architecture (no backend required)
- Hash-based routing for GitHub Pages compatibility
- Component-scoped state management (no centralized store)
- Chart.js for performance visualization

---

## 2. System Context

### 2.1 System Overview

The Leaderboard UI serves as the public-facing interface for the tau2-bench benchmark, enabling users to explore model rankings, compare performance metrics, and examine execution trajectories.

```mermaid
graph TB
    subgraph "Users"
        Researcher["👤 Researcher"]
        Developer["👤 Developer"]
        Contributor["👤 Contributor"]
    end

    subgraph "tau2-bench Leaderboard UI"
        WebApp["🌐 React SPA"]
    end

    subgraph "Static Data Sources"
        Submissions["📦 Submission JSON Files"]
        TaskData["📋 Task Definitions"]
        Trajectories["📜 Trajectory Logs"]
        Policies["📝 Domain Policies"]
    end

    subgraph "External"
        GitHub["🐙 GitHub Pages"]
        CDN["📡 Chart.js CDN"]
    end

    Researcher --> WebApp
    Developer --> WebApp
    Contributor --> WebApp

    WebApp --> Submissions
    WebApp --> TaskData
    WebApp --> Trajectories
    WebApp --> Policies

    GitHub --> WebApp
    CDN --> WebApp

    classDef user fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef app fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef data fill:#FFF3E0,stroke:#EF6C00,stroke-width:2px,color:#E65100
    classDef external fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px,color:#4A148C

    class Researcher,Developer,Contributor user
    class WebApp app
    class Submissions,TaskData,Trajectories,Policies data
    class GitHub,CDN external
```

### 2.2 Stakeholders

| Stakeholder           | Role         | Interest                                               |
|-----------------------|--------------|--------------------------------------------------------|
| ML Researchers        | Primary User | Compare model performance, analyze trajectories        |
| Developers            | Primary User | Understand benchmark structure, contribute submissions |
| Benchmark Maintainers | Operator     | Update leaderboard, verify submissions                 |
| Open Source Community | Contributor  | Submit new model results, suggest improvements         |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID   | Requirement                                                  | Priority |
|------|--------------------------------------------------------------|----------|
| FR-1 | Display model rankings with Pass^k metrics                   | High     |
| FR-2 | Filter results by domain (overall, retail, airline, telecom) | High     |
| FR-3 | Visualize performance trends via charts                      | High     |
| FR-4 | Explore execution trajectories for submissions               | Medium   |
| FR-5 | Browse task definitions and policies                         | Medium   |
| FR-6 | Distinguish standard vs custom submissions                   | Medium   |
| FR-7 | Deep-link to specific views via URL                          | Low      |

### 3.2 Non-Functional Requirements

| Category        | Requirement         | Target                        |
|-----------------|---------------------|-------------------------------|
| Performance     | Initial load time   | < 2 seconds                   |
| Scalability     | Support submissions | 100+ models                   |
| Accessibility   | Mobile responsive   | All screen sizes              |
| Deployment      | Static hosting      | GitHub Pages compatible       |
| Browser Support | Modern browsers     | Chrome, Firefox, Safari, Edge |

---

## 4. Architecture Overview

### 4.1 Architectural Style

**Single Page Application (SPA) with Static Data:**

The application follows a static-first architecture where all data is pre-generated JSON files served alongside the application. There is no backend server - all processing happens client-side.

**Why this style:**

- Zero operational overhead (no servers to maintain)
- GitHub Pages deployment (free, reliable hosting)
- Fast initial load (data co-located with app)
- Easy contribution workflow (submit JSON files via PR)

### 4.2 High-Level Architecture

```mermaid
graph TB
    subgraph "Browser"
        subgraph "React Application"
            App["📱 App.jsx<br/>Router & Navigation"]

            subgraph "Views"
                Home["🏠 Home View"]
                LB["📊 Leaderboard"]
                TV["🔍 TrajectoryVisualizer"]
            end

            subgraph "Shared"
                State["💾 Component State"]
                Storage["🗄️ localStorage"]
            end
        end

        ChartJS["📈 Chart.js"]
    end

    subgraph "Static Assets /public"
        Manifest["📋 manifest.json"]
        SubFiles["📦 submissions/*.json"]
        TaskFiles["📝 task-data/*.json"]
        TrajFiles["📜 trajectories/*.json"]
    end

    App --> Home
    App --> LB
    App --> TV

    LB --> State
    LB --> Storage
    LB --> ChartJS

    TV --> State

    LB -.fetch.-> Manifest
    LB -.fetch.-> SubFiles
    TV -.fetch.-> SubFiles
    TV -.fetch.-> TaskFiles
    TV -.fetch.-> TrajFiles

    classDef router fill:#BBDEFB,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef view fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef shared fill:#FFE0B2,stroke:#EF6C00,stroke-width:2px,color:#E65100
    classDef lib fill:#E1BEE7,stroke:#7B1FA2,stroke-width:2px,color:#4A148C
    classDef data fill:#FFECB3,stroke:#FF8F00,stroke-width:2px,color:#E65100

    class App router
    class Home,LB,TV view
    class State,Storage shared
    class ChartJS lib
    class Manifest,SubFiles,TaskFiles,TrajFiles data
```

---

## 5. Component Design

### 5.1 Component Hierarchy

```mermaid
graph TB
    subgraph "App Component"
        App["App.jsx"]
        Nav["Navigation Bar"]
        Footer["Footer"]
    end

    subgraph "Home View"
        Hero["Hero Section"]
        News["News Timeline"]
    end

    subgraph "Leaderboard Component"
        LBControls["Controls Panel"]
        LBTable["Table View"]
        LBChart["Chart View"]
        LBModal["Submission Modal"]

        subgraph "Controls"
            ViewToggle["View Toggle<br/>Table | Chart"]
            DomainToggle["Domain Filter<br/>Overall | Retail | Airline | Telecom"]
            TypeFilter["Submission Type<br/>Standard | Custom"]
        end
    end

    subgraph "TrajectoryVisualizer Component"
        TVHeader["View Mode Toggle"]

        subgraph "Trajectories Mode"
            SubList["Submission List"]
            TrajList["Trajectory List"]
            ConvView["Conversation Viewer"]
            ConfigModal["Config Modal"]
        end

        subgraph "Tasks Mode"
            DomainSelect["Domain Selector"]
            TaskGrid["Task Card Grid"]
            TaskDetail["Task Detail View"]
        end
    end

    App --> Nav
    App --> Hero
    App --> News
    App --> Footer

    App --> LBControls
    LBControls --> ViewToggle
    LBControls --> DomainToggle
    LBControls --> TypeFilter
    App --> LBTable
    App --> LBChart
    App --> LBModal

    App --> TVHeader
    TVHeader --> SubList
    SubList --> TrajList
    TrajList --> ConvView
    TrajList --> ConfigModal

    TVHeader --> DomainSelect
    DomainSelect --> TaskGrid
    TaskGrid --> TaskDetail

    classDef root fill:#BBDEFB,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef section fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef control fill:#FFE0B2,stroke:#EF6C00,stroke-width:2px,color:#E65100
    classDef view fill:#E1BEE7,stroke:#7B1FA2,stroke-width:2px,color:#4A148C

    class App root
    class Nav,Footer,Hero,News,LBControls,TVHeader section
    class ViewToggle,DomainToggle,TypeFilter,SubList,DomainSelect control
    class LBTable,LBChart,LBModal,TrajList,ConvView,ConfigModal,TaskGrid,TaskDetail view
```

### 5.2 Component Descriptions

#### App.jsx (Root Component)

- **Purpose:** Main orchestrator for routing and navigation
- **Responsibilities:** Hash-based routing, mobile menu toggle, view rendering
- **Technologies:** React 19, CSS
- **Dependencies:** All view components

#### Leaderboard.jsx

- **Purpose:** Display model performance rankings and metrics
- **Responsibilities:** Load submissions, render table/chart, handle filtering/sorting
- **Technologies:** React, Chart.js, localStorage
- **Dependencies:** Static submission JSON files

#### TrajectoryVisualizer.jsx

- **Purpose:** Explore execution trajectories and task definitions
- **Responsibilities:** Browse trajectories, display conversations, show task details
- **Technologies:** React
- **Dependencies:** Submission files, trajectory files, task data files

---

## 6. Data Architecture

### 6.1 Data Model

```mermaid
erDiagram
    MANIFEST ||--o{ SUBMISSION : contains
    MANIFEST {
        array submissions "List of submission directory names"
    }

    SUBMISSION ||--o{ DOMAIN_RESULT : has
    SUBMISSION ||--o{ TRAJECTORY_FILE : may_have
    SUBMISSION {
        string model_name "Model identifier"
        string model_organization "Organization name"
        string submission_date "ISO date"
        string submission_type "standard or custom"
        boolean is_new "Recently added flag"
        boolean trajectories_available "Has trajectory files"
        object methodology "Custom scaffold details"
        object contact "Contact information"
    }

    DOMAIN_RESULT {
        string domain "retail, airline, or telecom"
        float pass_1 "Pass@1 rate"
        float pass_2 "Pass@2 rate"
        float pass_3 "Pass@3 rate"
        float pass_4 "Pass@4 rate"
        float avg_cost "Average cost per task"
    }

    TRAJECTORY_FILE ||--o{ SIMULATION : contains
    TRAJECTORY_FILE {
        string filename "Trajectory file name"
        object info "Reproduction config"
    }

    SIMULATION ||--o{ MESSAGE : contains
    SIMULATION {
        int task_index "Task number"
        float reward "Final reward"
        boolean success "Task completed"
        array actions "Actions taken"
    }

    MESSAGE {
        string role "agent, user, or tool"
        string content "Message text"
        int turn "Turn number"
        object tool_calls "Tool invocations"
    }

    TASK_DATA ||--o{ TASK : contains
    TASK_DATA {
        string domain "Domain name"
    }

    TASK {
        int id "Task identifier"
        string description "Task description"
        object user_scenario "User context"
        object evaluation "Success criteria"
        object initial_state "Starting environment"
    }
```

### 6.2 Data Flow - Leaderboard

```mermaid
flowchart LR
    subgraph "Data Loading"
        A["🚀 Component Mount"] --> B["📋 Fetch manifest.json"]
        B --> C["📦 Parallel fetch<br/>all submission.json"]
        C --> D["⚙️ Transform &<br/>Calculate Averages"]
    end

    subgraph "State Management"
        D --> E["💾 setPassKData"]
        E --> F{"📊 View Mode?"}
    end

    subgraph "Rendering"
        F -->|Table| G["🗂️ Render Table<br/>with Sorting"]
        F -->|Chart| H["📈 Initialize<br/>Chart.js"]
    end

    subgraph "User Interactions"
        I["🖱️ Filter Change"] --> J["🔄 Re-filter Data"]
        J --> F
        K["🖱️ Sort Click"] --> L["🔄 Re-sort Data"]
        L --> G
        M["🖱️ Model Click"] --> N["📋 Show Modal"]
    end

    classDef load fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef state fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef render fill:#FFF3E0,stroke:#EF6C00,stroke-width:2px,color:#E65100
    classDef interact fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px,color:#4A148C

    class A,B,C,D load
    class E,F state
    class G,H render
    class I,J,K,L,M,N interact
```

### 6.3 Data Flow - Trajectory Visualizer

```mermaid
flowchart TB
    subgraph "Mode Selection"
        Start["🚀 Component Mount"] --> Mode{"📂 View Mode?"}
    end

    subgraph "Trajectories Path"
        Mode -->|Trajectories| T1["📋 Load Submissions"]
        T1 --> T2["🖱️ Select Submission"]
        T2 --> T3["🔍 HEAD requests<br/>probe trajectory files"]
        T3 --> T4["📜 Load Trajectory JSON"]
        T4 --> T5["💬 Display Conversation<br/>limit: 60 messages"]
    end

    subgraph "Tasks Path"
        Mode -->|Tasks| K1["🗂️ Select Domain"]
        K1 --> K2["📝 Fetch tasks.json<br/>limit: 50 tasks"]
        K2 --> K3["📜 Fetch policy.md"]
        K3 --> K4["🖱️ Select Task"]
        K4 --> K5["📋 Show Task Detail<br/>+ Policy + Results"]
    end

    classDef mode fill:#BBDEFB,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef traj fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef task fill:#FFE0B2,stroke:#EF6C00,stroke-width:2px,color:#E65100

    class Start,Mode mode
    class T1,T2,T3,T4,T5 traj
    class K1,K2,K3,K4,K5 task
```

---

## 7. Routing Architecture

### 7.1 Hash-Based Navigation

```mermaid
stateDiagram-v2
    [*] --> Home: Default / Invalid Hash

    Home --> Leaderboard: #leaderboard
    Home --> TrajectoryVisualizer: #trajectory-visualizer

    Leaderboard --> Home: #home
    Leaderboard --> TrajectoryVisualizer: #trajectory-visualizer

    TrajectoryVisualizer --> Home: #home
    TrajectoryVisualizer --> Leaderboard: #leaderboard

    state Home {
        [*] --> HeroSection
        HeroSection --> NewsSection
    }

    state Leaderboard {
        [*] --> TableView
        TableView --> ChartView: Toggle
        ChartView --> TableView: Toggle
        TableView --> SubmissionModal: Click Model
        ChartView --> SubmissionModal: Click Model
    }

    state TrajectoryVisualizer {
        [*] --> TrajectoriesMode
        TrajectoriesMode --> TasksMode: Toggle
        TasksMode --> TrajectoriesMode: Toggle
    }
```

### 7.2 URL Structure

| Route                    | View                 | Description                     |
|--------------------------|----------------------|---------------------------------|
| `#home`                  | Home                 | Landing page with hero and news |
| `#leaderboard`           | Leaderboard          | Model rankings and metrics      |
| `#trajectory-visualizer` | TrajectoryVisualizer | Trajectory and task explorer    |
| `(empty)`                | Home                 | Redirects to #home              |

---

## 8. User Interactions

### 8.1 Leaderboard User Journey

```mermaid
sequenceDiagram
    actor User
    participant App
    participant Leaderboard
    participant Storage as localStorage
    participant Data as Static Files

    User->>App: Navigate to #leaderboard
    App->>Leaderboard: Render component
    Leaderboard->>Storage: Load saved preferences
    Storage-->>Leaderboard: view, domain, sort settings
    Leaderboard->>Data: Fetch manifest.json
    Data-->>Leaderboard: submission list
    Leaderboard->>Data: Fetch all submission.json (parallel)
    Data-->>Leaderboard: submission data
    Leaderboard->>Leaderboard: Transform & aggregate data
    Leaderboard-->>User: Display table/chart

    User->>Leaderboard: Change domain filter
    Leaderboard->>Storage: Save preference
    Leaderboard->>Leaderboard: Re-filter data
    Leaderboard-->>User: Updated view

    User->>Leaderboard: Click model name
    Leaderboard-->>User: Show submission modal

    User->>Leaderboard: Toggle to chart view
    Leaderboard->>Storage: Save preference
    Leaderboard->>Leaderboard: Initialize Chart.js
    Leaderboard-->>User: Display chart
```

### 8.2 Trajectory Explorer User Journey

```mermaid
sequenceDiagram
    actor User
    participant App
    participant TV as TrajectoryVisualizer
    participant Data as Static Files

    User->>App: Navigate to #trajectory-visualizer
    App->>TV: Render component
    TV->>Data: Fetch manifest.json
    Data-->>TV: submission list
    TV->>Data: Fetch submission.json files
    Data-->>TV: submission metadata
    TV-->>User: Display submission list

    User->>TV: Select submission
    TV->>Data: HEAD requests to probe trajectories
    Data-->>TV: Available trajectory files
    TV-->>User: Display trajectory list

    User->>TV: Select trajectory
    TV->>Data: Fetch trajectory JSON
    Data-->>TV: Full trajectory data
    TV-->>User: Display simulations

    User->>TV: Select simulation
    TV-->>User: Display conversation (60 msg limit)

    User->>TV: Click config button
    TV-->>User: Show reproduction config modal
```

### 8.3 Task Browser User Journey

```mermaid
sequenceDiagram
    actor User
    participant TV as TrajectoryVisualizer
    participant Data as Static Files

    User->>TV: Switch to Tasks mode
    TV-->>User: Display domain selector

    User->>TV: Select domain (e.g., retail)
    TV->>Data: Fetch tasks.json (50 task limit)
    Data-->>TV: Task definitions
    TV->>Data: Fetch policy.md
    Data-->>TV: Policy content
    TV-->>User: Display task grid

    User->>TV: Click task card
    TV-->>User: Show task detail view
    Note over User,TV: Shows description, scenario,<br/>evaluation criteria, initial state,<br/>policy, and simulation results
```

---

## 9. State Management

### 9.1 State Architecture

```mermaid
graph TB
    subgraph "App State"
        AppState["currentView<br/>mobileMenuOpen"]
    end

    subgraph "Leaderboard State"
        subgraph "View State"
            LBView["leaderboardView<br/>domain<br/>sortColumn<br/>sortDirection"]
        end

        subgraph "Filter State"
            LBFilter["showStandard<br/>showCustom<br/>showFilterInfo"]
        end

        subgraph "Data State"
            LBData["passKData<br/>fullSubmissionData<br/>isLoading<br/>loadError"]
        end

        subgraph "UI State"
            LBUI["chartInstance<br/>showModal<br/>selectedSubmission<br/>modalClosing"]
        end
    end

    subgraph "TrajectoryVisualizer State"
        subgraph "Mode State"
            TVMode["viewMode<br/>selectedDomain"]
        end

        subgraph "Selection State"
            TVSelect["selectedSubmission<br/>selectedTrajectory<br/>selectedTask"]
        end

        subgraph "Data State "
            TVData["submissions<br/>availableTrajectories<br/>taskData<br/>loading<br/>error"]
        end

        subgraph "Modal State"
            TVModal["showConfigModal<br/>modalClosing"]
        end
    end

    subgraph "Persistence"
        LS["localStorage"]
    end

    LBView <--> LS
    LBFilter <--> LS

    classDef appState fill:#BBDEFB,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef lbState fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef tvState fill:#FFE0B2,stroke:#EF6C00,stroke-width:2px,color:#E65100
    classDef persist fill:#E1BEE7,stroke:#7B1FA2,stroke-width:2px,color:#4A148C

    class AppState appState
    class LBView,LBFilter,LBData,LBUI lbState
    class TVMode,TVSelect,TVData,TVModal tvState
    class LS persist
```

### 9.2 localStorage Keys

| Key               | Type    | Component   | Description                               |
|-------------------|---------|-------------|-------------------------------------------|
| `leaderboardView` | string  | Leaderboard | 'table' or 'chart'                        |
| `domain`          | string  | Leaderboard | 'overall', 'retail', 'airline', 'telecom' |
| `sortColumn`      | string  | Leaderboard | 'pass1', 'pass2', 'pass3', 'pass4'        |
| `sortDirection`   | string  | Leaderboard | 'asc' or 'desc'                           |
| `showStandard`    | boolean | Leaderboard | Show standard submissions                 |
| `showCustom`      | boolean | Leaderboard | Show custom submissions                   |

---

## 10. Deployment Architecture

### 10.1 Build & Deploy Pipeline

```mermaid
flowchart LR
    subgraph "Development"
        Dev["👨‍💻 Developer"]
        Code["📝 Source Code"]
    end

    subgraph "Build Process"
        Vite["⚡ Vite Build"]
        Dist["📦 dist/"]
    end

    subgraph "Deployment"
        GHPages["🐙 GitHub Pages"]
        CDN["🌐 CDN"]
    end

    subgraph "Runtime"
        Browser["🖥️ User Browser"]
    end

    Dev --> Code
    Code --> Vite
    Vite --> Dist
    Dist --> GHPages
    GHPages --> Browser
    CDN --> Browser

    classDef dev fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef build fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef deploy fill:#FFF3E0,stroke:#EF6C00,stroke-width:2px,color:#E65100
    classDef runtime fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px,color:#4A148C

    class Dev,Code dev
    class Vite,Dist build
    class GHPages,CDN deploy
    class Browser runtime
```

### 10.2 File Structure (Production)

```mermaid
graph TB
    subgraph "dist/ (Build Output)"
        Index["index.html"]
        Assets["assets/<br/>*.js, *.css"]

        subgraph "public/"
            Manifest["submissions/manifest.json"]
            Submissions["submissions/*/*.json"]
            TaskData["task-data/domains/*/"]
            Images["*.png, *.svg"]
        end
    end

    Index --> Assets
    Index --> Manifest
    Assets --> Submissions
    Assets --> TaskData

    classDef html fill:#FFCDD2,stroke:#C62828,stroke-width:2px,color:#B71C1C
    classDef js fill:#BBDEFB,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef data fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef img fill:#FFE0B2,stroke:#EF6C00,stroke-width:2px,color:#E65100

    class Index html
    class Assets js
    class Manifest,Submissions,TaskData data
    class Images img
```

---

## 11. Performance Optimizations

### 11.1 Optimization Strategies

```mermaid
graph TB
    subgraph "Data Loading"
        Lazy["🔄 Lazy Loading<br/>Fetch on demand"]
        Parallel["⚡ Parallel Fetches<br/>Promise.all()"]
        Limit["📉 Data Limiting<br/>50 tasks, 60 messages"]
    end

    subgraph "Rendering"
        Conditional["🎯 Conditional Render<br/>View mode switching"]
        ChartMgmt["📊 Chart Management<br/>Destroy/recreate"]
        LocalStore["💾 localStorage<br/>Persist preferences"]
    end

    subgraph "Network"
        HEAD["🔍 HEAD Requests<br/>Probe file existence"]
        Static["📦 Static Assets<br/>CDN caching"]
        Bundle["📦 Vite Bundling<br/>Code splitting"]
    end

    classDef load fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef render fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef network fill:#FFF3E0,stroke:#EF6C00,stroke-width:2px,color:#E65100

    class Lazy,Parallel,Limit load
    class Conditional,ChartMgmt,LocalStore render
    class HEAD,Static,Bundle network
```

### 11.2 Performance Targets

| Metric       | Target  | Strategy              |
|--------------|---------|-----------------------|
| Initial Load | < 2s    | Vite bundling, CDN    |
| Data Fetch   | < 1s    | Parallel requests     |
| View Switch  | < 100ms | Conditional rendering |
| Chart Render | < 500ms | Canvas optimization   |
| Mobile Menu  | < 50ms  | CSS transitions       |

---

## 12. Technology Stack

### 12.1 Stack Overview

```mermaid
graph TB
    subgraph "Frontend"
        React["⚛️ React 19"]
        CSS["🎨 CSS 3"]
        ChartJS["📊 Chart.js"]
    end

    subgraph "Build & Dev"
        Vite["⚡ Vite 7"]
        ESLint["📝 ESLint 9"]
        npm["📦 npm"]
    end

    subgraph "Deployment"
        GHPages["🐙 gh-pages"]
        GitHub["🐙 GitHub Actions"]
    end

    subgraph "Data Format"
        JSON["📄 JSON"]
        Markdown["📝 Markdown"]
    end

    React --> Vite
    CSS --> Vite
    ChartJS --> React
    Vite --> GHPages
    ESLint --> Vite
    npm --> Vite

    classDef frontend fill:#61DAFB,stroke:#20232A,stroke-width:2px,color:#20232A
    classDef build fill:#646CFF,stroke:#1A1A2E,stroke-width:2px,color:white
    classDef deploy fill:#24292E,stroke:#1A1A2E,stroke-width:2px,color:white
    classDef data fill:#F7DF1E,stroke:#1A1A2E,stroke-width:2px,color:#1A1A2E

    class React,CSS,ChartJS frontend
    class Vite,ESLint,npm build
    class GHPages,GitHub deploy
    class JSON,Markdown data
```

### 12.2 Dependencies

| Package              | Version | Purpose                 |
|----------------------|---------|-------------------------|
| react                | ^19.1.0 | UI framework            |
| react-dom            | ^19.1.0 | DOM rendering           |
| vite                 | ^7.0.4  | Build tool & dev server |
| @vitejs/plugin-react | ^4.6.0  | Vite React plugin       |
| chart.js             | CDN     | Charting library        |
| gh-pages             | ^6.1.1  | GitHub Pages deployment |
| eslint               | ^9.30.1 | Code linting            |

---

## 13. Decision Log

### ADR-001: Static-First Architecture

**Date:** 2024-01-01
**Status:** Accepted

**Context:**
The leaderboard needs to display benchmark results without requiring a backend server for cost and maintenance reasons.

**Decision:**
Use static JSON files served alongside the React application, with all data processing happening client-side.

**Consequences:**

- Positive: Zero operational cost, simple deployment, no server maintenance
- Positive: GitHub Pages compatible, enables PR-based submission workflow
- Negative: Limited to client-side data processing
- Negative: No real-time updates (requires rebuild for new data)

### ADR-002: Hash-Based Routing

**Date:** 2024-01-01
**Status:** Accepted

**Context:**
Need client-side routing that works with static file hosting (GitHub Pages) without server-side configuration.

**Decision:**
Implement hash-based routing using `window.location.hash` instead of React Router.

**Consequences:**

- Positive: Works on any static host without server configuration
- Positive: Supports browser back/forward navigation
- Positive: Enables deep-linking to specific views
- Negative: URLs contain `#` (less clean than path-based routing)
- Negative: No library support (manual implementation)

### ADR-003: Component-Scoped State

**Date:** 2024-01-01
**Status:** Accepted

**Context:**
Need state management for view preferences, filters, and loaded data.

**Decision:**
Use React hooks (useState, useEffect) with localStorage for persistence instead of a centralized state management library.

**Consequences:**

- Positive: Lightweight, no additional dependencies
- Positive: Clear data ownership per component
- Positive: User preferences persist across sessions
- Negative: No state sharing between components
- Negative: localStorage sync adds some complexity

---

## 14. Appendices

### Glossary

| Term                | Definition                                                      |
|---------------------|-----------------------------------------------------------------|
| Pass^k              | Success rate metric where k attempts are allowed per task       |
| Trajectory          | Complete execution trace of agent-user-environment interactions |
| Domain              | Benchmark category (retail, airline, telecom)                   |
| Standard Submission | Uses default scaffold with unmodified prompts                   |
| Custom Submission   | Uses modified scaffold (multi-model, custom tools, etc.)        |

### References

1. [tau2-bench Repository](https://github.com/tau2-bench)
2. [React Documentation](https://react.dev)
3. [Vite Documentation](https://vite.dev)
4. [Chart.js Documentation](https://www.chartjs.org/docs)
5. [GitHub Pages Documentation](https://pages.github.com)
