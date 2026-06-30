from langgraph.graph import StateGraph, END, START
from pydantic import BaseModel
from dataclasses import dataclass, field
from typing import Optional, List
from agent.nodes.intent_node import CalendarIntentNode
from agent.nodes.calender_action_node import CalendarActionNode
from agent.nodes.calendar_response_node import CalendarResponseNode
from langgraph.checkpoint.memory import MemorySaver
# from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import BaseMessage
from agent.nodes.load_memory_node import LoadMemoryNode
from agent.nodes.save_memory_node import SaveMemoryNode



@dataclass
class GraphState:
    user_id: str
    user_message: str 
    messages: List[BaseMessage] = field(default_factory=list)

    intent: Optional[str] = None            
    action_params: Optional[dict] = None    
    calendar_result: Optional[str] = None
    mom_result: Optional[str] = None
    response_message: Optional[str] = None

graph = StateGraph(GraphState)
graph.add_node("load_memory", LoadMemoryNode())
graph.add_node("intent_node", CalendarIntentNode())
graph.add_node("action_node", CalendarActionNode())
graph.add_node("response_node", CalendarResponseNode())
graph.add_node("save_memory", SaveMemoryNode())


graph.add_edge(START, "load_memory")
graph.add_edge("load_memory", "intent_node")
graph.add_edge("intent_node", "action_node")
graph.add_edge("action_node", "response_node")
graph.add_edge("response_node", "save_memory")
graph.add_edge("save_memory", END)
workflow = graph.compile()