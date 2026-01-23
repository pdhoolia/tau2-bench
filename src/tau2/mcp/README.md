# Tau2-Bench MCP Servers

FastMCP servers wrapping the Tau2-Bench domain tools for use with MCP-compatible AI agents.

## Supported Domains

| Domain      | Tools | Description                                                |
|-------------|-------|------------------------------------------------------------|
| **Airline** | 14    | Flight booking, reservations, cancellations, modifications |
| **Retail**  | 15    | E-commerce orders, returns, exchanges, user management     |
| **Telecom** | 13    | Customer accounts, billing, line management, data usage    |

## Installation

```bash
# Install tau2-bench with MCP support
pip install -e ".[mcp]"
```

## Usage

### Unified Command (Recommended)

```bash
# Run airline server (default) with stdio
python -m tau2.mcp

# Run specific domain
python -m tau2.mcp --domain airline
python -m tau2.mcp --domain retail
python -m tau2.mcp --domain telecom

# Run with HTTP transport
python -m tau2.mcp --domain airline --transport http --port 8000
python -m tau2.mcp --domain retail --transport http --port 8001
python -m tau2.mcp --domain telecom --transport http --port 8002
```

### Individual Domain Servers

```bash
# Airline
python -m tau2.mcp.airline_server
python -m tau2.mcp.airline_server --transport http --port 8000

# Retail
python -m tau2.mcp.retail_server
python -m tau2.mcp.retail_server --transport http --port 8001

# Telecom
python -m tau2.mcp.telecom_server
python -m tau2.mcp.telecom_server --transport http --port 8002
```

### Custom Database Path

```bash
python -m tau2.mcp --domain airline --db-path /path/to/custom/db.json
```

## MCP Configuration

### For Claude Desktop (stdio)

Add to your Claude Desktop MCP config:

```json
{
  "mcpServers": {
    "tau2-airline": {
      "command": "python",
      "args": ["-m", "tau2.mcp", "--domain", "airline"],
      "cwd": "/path/to/tau2-bench",
      "env": {
        "PYTHONPATH": "/path/to/tau2-bench/src"
      }
    },
    "tau2-retail": {
      "command": "python",
      "args": ["-m", "tau2.mcp", "--domain", "retail"],
      "cwd": "/path/to/tau2-bench",
      "env": {
        "PYTHONPATH": "/path/to/tau2-bench/src"
      }
    },
    "tau2-telecom": {
      "command": "python",
      "args": ["-m", "tau2.mcp", "--domain", "telecom"],
      "cwd": "/path/to/tau2-bench",
      "env": {
        "PYTHONPATH": "/path/to/tau2-bench/src"
      }
    }
  }
}
```

### For Remote Access (HTTP)

Start the servers:

```bash
python -m tau2.mcp --domain airline --transport http --port 8000
python -m tau2.mcp --domain retail --transport http --port 8001
python -m tau2.mcp --domain telecom --transport http --port 8002
```

Then connect using the MCP endpoints:

- Airline: `http://localhost:8000/mcp`
- Retail: `http://localhost:8001/mcp`
- Telecom: `http://localhost:8002/mcp`

## Available Tools

### Airline Domain (14 tools)

#### Read Tools

- `get_user_details(user_id)` - Get user profile with reservations
- `get_reservation_details(reservation_id)` - Get reservation details
- `list_all_airports()` - List all available airports (20 IATA codes)
- `search_direct_flight(origin, destination, date)` - Search direct flights
- `search_onestop_flight(origin, destination, date)` - Search connecting flights
- `get_flight_status(flight_number, date)` - Get flight status

#### Write Tools

- `book_reservation(...)` - Create a new reservation
- `cancel_reservation(reservation_id)` - Cancel a reservation
- `update_reservation_passengers(reservation_id, passengers)` - Update passenger info
- `update_reservation_baggages(reservation_id, ...)` - Update baggage info
- `update_reservation_flights(reservation_id, ...)` - Change flights
- `send_certificate(user_id, amount)` - Send travel certificate to user

#### Utility Tools

- `calculate(expression)` - Evaluate mathematical expressions
- `transfer_to_human_agents(summary)` - Transfer to human support

### Retail Domain (15 tools)

#### Read Tools

- `get_user_details(user_id)` - Get user profile with orders
- `get_order_details(order_id)` - Get order details
- `get_product_details(product_id)` - Get product inventory details
- `list_all_product_types()` - List all products (50 types)
- `find_user_id_by_email(email)` - Find user by email
- `find_user_id_by_name_zip(first_name, last_name, zip)` - Find user by name and zip

#### Write Tools

- `cancel_pending_order(order_id, reason)` - Cancel a pending order
- `modify_pending_order_address(order_id, ...)` - Change shipping address
- `modify_pending_order_items(order_id, ...)` - Modify order items
- `modify_pending_order_payment(order_id, payment_method_id)` - Change payment method
- `modify_user_address(user_id, ...)` - Update user's default address
- `exchange_delivered_order_items(order_id, ...)` - Exchange delivered items
- `return_delivered_order_items(order_id, ...)` - Return delivered items

#### Utility Tools

- `calculate(expression)` - Evaluate mathematical expressions
- `transfer_to_human_agents(summary)` - Transfer to human support

### Telecom Domain (13 tools)

#### Read Tools

- `get_customer_by_id(customer_id)` - Get customer by ID
- `get_customer_by_phone(phone_number)` - Find customer by phone
- `get_customer_by_name(full_name, dob)` - Find customer by name and DOB
- `get_details_by_id(id)` - Get details for any ID (customer, line, device, bill, plan)
- `get_bills_for_customer(customer_id, limit)` - Get customer's bills
- `get_data_usage(customer_id, line_id)` - Get data usage for a line

#### Write Tools

- `suspend_line(customer_id, line_id, reason)` - Suspend a line
- `resume_line(customer_id, line_id)` - Resume a suspended line
- `enable_roaming(customer_id, line_id)` - Enable international roaming
- `disable_roaming(customer_id, line_id)` - Disable international roaming
- `refuel_data(customer_id, line_id, gb_amount)` - Add data to a line
- `send_payment_request(customer_id, bill_id)` - Send payment request

#### Utility Tools

- `transfer_to_human_agents(summary)` - Transfer to human support

## API Reference

### Programmatic Usage

```python
from tau2.mcp import (
    create_airline_mcp_server,
    create_retail_mcp_server,
    create_telecom_mcp_server,
)

# Create servers with default databases
airline_mcp = create_airline_mcp_server()
retail_mcp = create_retail_mcp_server()
telecom_mcp = create_telecom_mcp_server()

# Create server with custom database
airline_mcp = create_airline_mcp_server(db_path="/path/to/db.json")

# Run with stdio
airline_mcp.run()

# Run with HTTP
airline_mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

## Database Information

Each domain uses its own database:

| Domain  | File      | Format | Contents                                |
|---------|-----------|--------|-----------------------------------------|
| Airline | `db.json` | JSON   | 300 flights, 500 users, reservations    |
| Retail  | `db.json` | JSON   | 50 product types, users, orders         |
| Telecom | `db.toml` | TOML   | Customers, lines, plans, bills, devices |

Databases are loaded at server startup. Write operations modify the in-memory state but do not persist to disk by default.

## Error Handling

Tool errors are returned as structured responses:

```json
{
  "error": "User not found"
}
```

Business logic errors (invalid user, order not found, insufficient balance, etc.) are caught and returned in this format rather than raising exceptions.
