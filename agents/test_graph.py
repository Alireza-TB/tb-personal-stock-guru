from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph


# --- State ---
# The shared data structure that flows through every node.
# Every field here can be read and updated by any node in the graph.
class State(TypedDict):
    messages: list[str]


# --- Node ---
# A node is just a plain function: it receives State, does work, and returns
# a dict of only the fields it wants to update (merged back by LangGraph).
def greeter(state: State) -> dict:
    llm = ChatAnthropic(model="claude-haiku-4-5")
    prompt = "Say hello and introduce yourself as an investment research assistant in 2 sentences."
    response = llm.invoke(prompt)
    # response.content is the raw text string from Claude
    return {"messages": state["messages"] + [response.content]}


# --- Graph construction ---
# StateGraph(State) tells LangGraph what the shared state schema looks like.
builder = StateGraph(State)

# Register the greeter function as a node named "greeter"
builder.add_node("greeter", greeter)

# Wire up the edges: START → greeter → END
builder.add_edge(START, "greeter")
builder.add_edge("greeter", END)

# Compile turns the blueprint into a runnable object
graph = builder.compile()


if __name__ == "__main__":
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)

    # Invoke with an empty initial state — messages starts as an empty list
    result = graph.invoke({"messages": []})

    print("Final state:")
    for msg in result["messages"]:
        print(msg)
