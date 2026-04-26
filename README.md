# Customer Service Agent
The task of a customer agent can be broadly divided into two categories:
1. Logging new support tickets
2. Delivering the status of existing support tickets
3. Prioritizing Support tickets according to time elapsed

# Assumptions
For this assignment, since we are **not** assuming Jira integrations as we will need an enterprise grade DB to search for relevant queries.

We will be using a simple json that logs the following data:
1. Ticket ID
2. Ticket Category
3. User email who logged the ticket
4. Date and Time when the ticket is logged
5. Ticket Description
6. Status of the Ticket (Yet to Start, WIP, Resolved)

This will keep the Customer Service Management at a small scale. As the number of logs grow we can opt for bigger databases to store the ticket info (not necessarily Jira)

For this assignment we are going to assume that the customer service agent is in the Food Delivery Industry. As such the knowledge base of the agent will limited to a **Customer Service Policy Document** that has been created as an example

# Agent Workflow

~~~mermaid 
flowchart 
    A[User Query] --> B[Thought]
    B --> C[Action]
    C --> D[Tool]
    D --> E[Observation]
    E --> B
    B ----> F[Agent Answer]
~~~

## Tools
We will be using a simple Langchain Agent that has access to the following custom tools:
1. Create Ticket Tool
2. Status Check Tool
3. Time Elapsed Calculation Tool
4. Knowledge Base Reference Tool

# Libraries and Frameworks
1. Langchain
2. Streamlit