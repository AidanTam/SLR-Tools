pip install streamlit
pip install --upgrade streamlit
pip install plotly
pip install --upgrade plotly
pip install statsmodels
pip install --upgrade statsmodels
pip install scipy
pip install --upgrade scipy
pip install struct
pip install --upgrade struct
pip install subprocess
pip install --upgrade subprocess
pip install wordcloud
pip install --upgrade protobuf

Reg.exe add "HKCU\SOFTWARE\Classes\Directory\Background\shell\RPA Tools\command" /ve /t REG_SZ /d "powershell.exe -noexit streamlit run C:\ProgramData\Anaconda3\Lib\site-packages\pyrpa\UI\rpa_tools.py" /f
Reg.exe add "HKCU\SOFTWARE\Classes\Directory\Background\shell\Jupyter Notebook\command" /ve /t REG_SZ /d "powershell.exe -noexit jupyter notebook" /f