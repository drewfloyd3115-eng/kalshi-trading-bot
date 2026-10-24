"""Standalone deployment option: streamlit run cfb_model_app.py"""
import streamlit as st
from cfb_model.ui import render_model_ui

st.set_page_config(page_title="CFB Prediction Lab — Paper Only",page_icon="🏈",layout="centered")
render_model_ui()
