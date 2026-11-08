# import matplotlib.pyplot as plt
# import matplotlib.dates as mdates
# import pandas as pd
# import streamlit as st 
# import datetime
# import random
# from pptx import Presentation
# from pptx.util import Inches
# import io
# import numpy as np
# from matplotlib.ticker import MaxNLocator, MultipleLocator
# import matplotlib.colors as mcolors
# import json

# def remove_placeholders_from_slide(slide):
#     for shape in slide.shapes:
#         if not shape.is_placeholder:
#             continue
#         sp = shape._element
#         sp.getparent().remove(sp)

# def save_fig_to_presentation(fig_list, presentation_path="charts_presentation.pptx"):
#     prs = Presentation()
#     for fig in fig_list:
#         slide = prs.slides.add_slide(prs.slide_layouts[5])
#         remove_placeholders_from_slide(slide)
#         buf = io.BytesIO()
#         fig.savefig(buf, format='png', bbox_inches='tight')
#         buf.seek(0)
#         available_width = prs.slide_width
#         available_height = prs.slide_height
#         tmp_pic = slide.shapes.add_picture(buf, 0, 0, width=available_width)
#         image_aspect_ratio = tmp_pic.width / tmp_pic.height
#         slide_aspect_ratio = available_width / available_height
#         if image_aspect_ratio > slide_aspect_ratio:
#             final_width = available_width
#             final_height = int(final_width / image_aspect_ratio)
#         else:
#             final_height = available_height
#             final_width = int(final_height * image_aspect_ratio)
#         left = (available_width - final_width) / 2
#         top = (available_height - final_height) / 2
#         slide.shapes._spTree.remove(tmp_pic._element)
#         slide.shapes.add_picture(buf, left, top, width=final_width, height=final_height)
#         buf.close()
#     prs.save(presentation_path)
#     return presentation_path

# def serialize_session_state(state):
#     serialized_state = {}
#     for key, value in state.items():
#         if isinstance(value, (datetime.date, datetime.datetime)):
#             serialized_state[key] = value.isoformat()
#         else:
#             serialized_state[key] = value
#     return serialized_state

# def deserialize_session_state(state_dict):
#     deserialized_state = {}
#     for key, value in state_dict.items():
#         if isinstance(value, str):
#             try:
#                 deserialized_state[key] = datetime.date.fromisoformat(value)
#             except ValueError:
#                 deserialized_state[key] = value
#         else:
#             deserialized_state[key] = value
#     return deserialized_state

# # Helper to auto-select a column (case-insensitive)
# def auto_select(col_list, target):
#     for i, col in enumerate(col_list):
#         if col.lower() == target.lower():
#             return i
#     return 0

# st.set_page_config(layout="wide")

# saved_progress_file = st.sidebar.file_uploader("Load Progress", type=['json'])
# if saved_progress_file is not None:
#     saved_state = json.load(saved_progress_file)
#     deserialized_state = deserialize_session_state(saved_state)
#     st.session_state.update(deserialized_state)
#     st.success("Progress loaded!")
#     st.info("Please upload the same data file used in the saved progress.")

# file = st.sidebar.file_uploader("Choose a data file")
# if file is not None:
#     data = pd.read_csv(file)
#     # Convert columns to a list for auto-selection
#     columns = list(data.columns)
#     # Auto-detect columns if they exist (case-insensitive)
#     date_idx = auto_select(columns, "Date")
#     grade_idx = auto_select(columns, "Grade")
#     crm_idx = auto_select(columns, "CRM")
#     elements_idx = auto_select(columns, "Element")
#     expected_idx = auto_select(columns, "Expected Value")
    
#     date_col = st.sidebar.selectbox('Date Column', columns, index=date_idx, key='date_col')
#     data[date_col] = pd.to_datetime(data[date_col])
#     grade_col = st.sidebar.selectbox('Grade Column', columns, index=grade_idx, key='grade_col')
#     CRM_col = st.sidebar.selectbox('CRM Column', columns, index=crm_idx, key='CRM_col')
#     try:
#         data[grade_col] = data[grade_col].astype(float)
#     except:
#         st.error('Make sure to choose the right grade column')
#     elementcolumn = st.sidebar.selectbox('Element Column', columns, index=elements_idx, key='elementcolumn')
#     elements = st.multiselect('Select Element', data[elementcolumn].unique(), key='element')
#     expected_val_col = st.sidebar.selectbox('Expected Value Column', columns, index=expected_idx, key='expected_val_col')
#     source_col = st.sidebar.selectbox('Categorical column', columns, key='source_col')
    
#     # --- New Optional Grouping Fields ---
#     optional_group_field_1 = st.sidebar.selectbox('Optional Grouping Field 1', ['None'] + columns, key='optional_group_field_1')
#     optional_group_field_2 = st.sidebar.selectbox('Optional Grouping Field 2', ['None'] + columns, key='optional_group_field_2')
#     optional_group_field_3 = st.sidebar.selectbox('Optional Grouping Field 3', ['None'] + columns, key='optional_group_field_3')
    
#     # --- Unit Field: determine source of unit
#     # If a unit column exists, offer that column along with a "Custom" option.
#     if any(col.lower() == "unit" for col in columns):
#         unit_options = [col for col in columns if col.lower() == "unit"]
#         unit_options.append("Custom")
#         unit_selection = st.sidebar.selectbox("Unit Source", unit_options, index=0, key="unit_option")
#         if unit_selection == "Custom":
#             custom_unit = st.sidebar.text_input("Enter Custom Unit", value="", key="custom_unit")
#             unit_col_name = None
#         else:
#             unit_col_name = unit_selection
#             # st.sidebar.write("Unit will be taken from column '" + unit_col_name + "' for each chart.")
#             custom_unit = None
#     else:
#         unit_options = ["%", "mg/L", "ppb", "Custom"]
#         unit_selection = st.sidebar.selectbox("Unit", unit_options, index=0, key="unit_option")
#         if unit_selection == "Custom":
#             custom_unit = st.sidebar.text_input("Enter Custom Unit", value="", key="custom_unit")
#             unit = None
#         else:
#             unit = unit_selection
#             custom_unit = None
#         unit_col_name = None
    
#     # --- SLR Text (default SLR currentYear) ---
#     slr_text = st.sidebar.text_input("SLR Text", value=f"SLR {datetime.datetime.now().year}", key="slr_text")
    
#     col1, col2, col3, col4, col5 = st.columns(5)
#     Point_color = col1.color_picker('Sample Color', '#7FA37F', key='Point_color')
#     failure_color = col2.color_picker('Failure Color', '#FF0000', key='failure_color')
#     twoSD_color = col3.color_picker('2 SD Color', '#B5ED38', key='twoSD_color')
#     threeSD_color = col4.color_picker('3 SD Color', '#7FA37F', key='threeSD_color')
#     show_summary = col5.checkbox('Show Summary', key='show_summary')
#     sdcalc = st.sidebar.checkbox('Expected Value + 1SD', key='sdcalc', help='Use this Failure Criteria based on the CRM certificate Expected Value and 1SD')
#     usemean = st.sidebar.checkbox('Mean value + 1SD', key='usemean' , help='Use this Failure Criteria based on the data mean and calculated SD')
#     UseUL_LW = st.sidebar.checkbox('Use an upper/lower limits fields', key='UseUL_LW')
#     if not UseUL_LW:
#         if not sdcalc:
#             twostd = st.sidebar.number_input('1st SD Threshold', value=2, key='twostd')
#             threestd = st.sidebar.number_input('2nd SD Threshold', value=3, key='threestd')
#         else:
#             std_col = st.sidebar.selectbox('SD Column', columns, key='std_col')
#             twostd = st.sidebar.number_input('1st SD Threshold', value=2, key='twostd')
#             threestd = st.sidebar.number_input('2nd SD Threshold', value=3, key='threestd')
#     else:
#         upperlimit_col = st.sidebar.selectbox('Upper Limit Column', columns, key='upperlimit_col')
#         lowerlimit_col = st.sidebar.selectbox('Lower Limit Column', columns, key='lowerlimit_col')
#     fig_list = []
#     allstats = []
#     x_text_rotation = st.sidebar.number_input('X Axis text rotation', value=0, key='x_text_rotation')
#     x_margin = st.sidebar.number_input('X axis margin', value=0.00, step=0.01, key='x_margin')
    
#     # Process charts for each element
#     for i, elem in enumerate(elements):
#         filtered = data[data[elementcolumn] == elem]
#         prefix = f"{i}_{elem}"
#         # CRM multi-select: filter the dataframe to include only selected CRMs.
#         selected_crms = st.multiselect('Select CRMs', filtered[CRM_col].unique(), key=f"CRM_{prefix}")
#         if not selected_crms:
#             selected_crms = list(filtered[CRM_col].unique())
#         filtered = filtered[filtered[CRM_col].isin(selected_crms)]
        
#         st.markdown(f"<h1 style='text-align: center; color: #7FA37F;'>Charts for {elem}</h1>", unsafe_allow_html=True)
        
#         # Loop over the unique CRM codes in the filtered dataframe.
#         for j, certificate in enumerate(filtered[CRM_col].unique()):
#             unique_key_prefix = f"{i}_{j}_{elem}_{certificate}"
#             min_grade_threshold = st.number_input('Min grade threshold', value=filtered[grade_col].min(), key=f"min_{unique_key_prefix}")
#             max_grade_threshold = st.number_input('Max grade threshold', value=filtered[grade_col].max(), key=f"max_{unique_key_prefix}")
#             # Further filter the data for this specific CRM code.
#             filtered_data = filtered[(filtered[grade_col] >= min_grade_threshold) & 
#                                      (filtered[grade_col] <= max_grade_threshold) & 
#                                      (filtered[CRM_col] == certificate)]
#             # --- Combine optional grouping fields ---
#             group_fields = []
#             if optional_group_field_1 != 'None':
#                 group_fields.append(optional_group_field_1)
#             if optional_group_field_2 != 'None':
#                 group_fields.append(optional_group_field_2)
#             if optional_group_field_3 != 'None':
#                 group_fields.append(optional_group_field_3)
            
#             if group_fields:
#                 grouped = filtered_data.groupby(group_fields)
#                 for grp_values, group_data in grouped:
#                     data_subset = group_data.copy()
#                     if isinstance(grp_values, tuple):
#                         group_label = " - ".join([str(val) for val in grp_values])
#                     else:
#                         group_label = str(grp_values)
#                     group_key = f"{unique_key_prefix}_{group_label}"

#                     x_axis_min = st.date_input("X axis min", key=f"x_min_{group_key}", value=data_subset[date_col].min())
#                     x_axis_max = st.date_input("X axis max", key=f"x_max_{group_key}", value=data_subset[date_col].max())
#                     y_axis_min = st.number_input('Y min', key=f"y_min_{group_key}", value=data_subset[grade_col].min() - data_subset[grade_col].std())
#                     y_axis_max = st.number_input('Y max', key=f"y_max_{group_key}", value=data_subset[grade_col].max() + data_subset[grade_col].std())
#                     labname = st.text_input('Lab Name', key=f"lab_{group_key}")
                    
#                     if not UseUL_LW:
#                         if not usemean:
#                             expected_val = data_subset[expected_val_col].mean()
#                             mean_value_au = data_subset[grade_col].mean()
#                             if not sdcalc:
#                                 standard_deviation = data_subset[grade_col].std()
#                                 data_subset['Upper Bound (2SD)'] = expected_val + (twostd * standard_deviation)
#                                 data_subset['Lower Bound (2SD)'] = expected_val - (twostd * standard_deviation)
#                                 data_subset['Upper Bound (3SD)'] = expected_val + (threestd * standard_deviation)
#                                 data_subset['Lower Bound (3SD)'] = expected_val - (threestd * standard_deviation)
#                             else:
#                                 if len(data_subset[std_col].unique()) == 1:
#                                     standard_deviation = data_subset[std_col].unique()[0]
#                                     data_subset['Upper Bound (2SD)'] = expected_val + (twostd * standard_deviation)
#                                     data_subset['Lower Bound (2SD)'] = expected_val - (twostd * standard_deviation)
#                                     data_subset['Upper Bound (3SD)'] = expected_val + (threestd * standard_deviation)
#                                     data_subset['Lower Bound (3SD)'] = expected_val - (threestd * standard_deviation)
#                                 else:
#                                     st.warning('There are multiple values in the STD column; please check the file for any errors')
#                         else:
#                             expected_val = data_subset[expected_val_col].mean()
#                             mean_value_au = data_subset[grade_col].mean()
#                             if not sdcalc:
#                                 standard_deviation = data_subset[grade_col].std()
#                                 data_subset['Upper Bound (2SD)'] = mean_value_au + (twostd * standard_deviation)
#                                 data_subset['Lower Bound (2SD)'] = mean_value_au - (twostd * standard_deviation)
#                                 data_subset['Upper Bound (3SD)'] = mean_value_au + (threestd * standard_deviation)
#                                 data_subset['Lower Bound (3SD)'] = mean_value_au - (threestd * standard_deviation)
#                             else:
#                                 if len(data_subset[std_col].unique()) == 1:
#                                     standard_deviation = data_subset[std_col].unique()[0]
#                                     data_subset['Upper Bound (2SD)'] = mean_value_au + (twostd * standard_deviation)
#                                     data_subset['Lower Bound (2SD)'] = mean_value_au - (twostd * standard_deviation)
#                                     data_subset['Upper Bound (3SD)'] = mean_value_au + (threestd * standard_deviation)
#                                     data_subset['Lower Bound (3SD)'] = mean_value_au - (threestd * standard_deviation)
#                                 else:
#                                     st.warning('There are multiple values in the STD column; please check the file for any errors')
#                     else:
#                         expected_val = data_subset[expected_val_col].mean()
#                         mean_value_au = data_subset[grade_col].mean()
#                         standard_deviation = data_subset[grade_col].std()
#                         data_subset['Upper Bound (3SD)'] = data_subset[upperlimit_col].mean()
#                         data_subset['Lower Bound (3SD)'] = data_subset[lowerlimit_col].mean()
                    
#                     data_subset = data_subset.sort_values(by=[date_col]).reset_index(drop=True)
#                     x_axis_min_dt = pd.to_datetime(x_axis_min)
#                     x_axis_max_dt = pd.to_datetime(x_axis_max) + pd.Timedelta(days=1)
#                     if x_axis_max_dt > x_axis_min_dt:
#                         data_subset = data_subset[(data_subset[date_col] >= x_axis_min_dt) & (data_subset[date_col] <= x_axis_max_dt)]
#                     elif x_axis_max_dt == x_axis_min_dt:
#                         data_subset = data_subset[data_subset[date_col].dt.date == x_axis_min]
#                     else:
#                         st.write('There is a problem with dates')
#                     data_subset['Sequence'] = range(0, len(data_subset))
#                     st.dataframe(data_subset)
#                     nbin = st.slider('Number of Ticks', 1, len(data_subset)-1, 3, key=f"nbin_{group_key}")
#                     data_subset['Sequence'] = data_subset['Sequence'].astype('category')
#                     num_samples = len(data_subset[grade_col])
#                     num_outliers = sum((data_subset[grade_col] > data_subset['Upper Bound (3SD)']) | (data_subset[grade_col] < data_subset['Lower Bound (3SD)']))
#                     bias = ((mean_value_au / data_subset[expected_val_col].iloc[0]) - 1) * 100
#                     percentage_outliers = (num_outliers / num_samples) * 100
#                     summary_data = {
#                         "Number of Samples": num_samples,
#                         "Mean": mean_value_au,
#                         "Expected Value": data_subset[expected_val_col].mean(),
#                         "Standard Deviation": standard_deviation,
#                         "Number of Outliers": num_outliers,
#                         "Bias (%)": bias,
#                         "Failure Rate (%)": percentage_outliers
#                     }
#                     summary_data_rounded = {k: round(v, 2) for k, v in summary_data.items()}
#                     if not UseUL_LW:
#                         summary_data2 = {
#                             'Element': elem,
#                             'Unit': None,  # will be set below
#                             'CRM': certificate,
#                             'Periode Range': f"{x_axis_min} - {x_axis_max}",
#                             "Number of Samples": num_samples,
#                             "Mean": mean_value_au,
#                             "Expected Value": data_subset[expected_val_col].mean(),
#                             "Standard Deviation": standard_deviation,
#                             "Number of Outliers": num_outliers,
#                             "Bias (%)": bias,
#                             "Failure Rate (%)": percentage_outliers,
#                             "Upper Bound (2SD)": mean_value_au + (twostd * standard_deviation),
#                             "Lower Bound (2SD)": mean_value_au - (twostd * standard_deviation),
#                             'Upper Bound (3SD)': mean_value_au + (threestd * standard_deviation),
#                             'Lower Bound (3SD)': mean_value_au - (threestd * standard_deviation)
#                         }
#                         # ← insert this block now:
#                         if isinstance(grp_values, tuple):
#                             for field, val in zip(group_fields, grp_values):
#                                 summary_data2[field] = val
#                         else:
#                             summary_data2[group_fields[0]] = grp_values
#                     else:
#                         summary_data2 = {
#                             'Element': elem,
#                             'Unit': None,  # will be set below
#                             'CRM': certificate,
#                             'Periode Range': f"{x_axis_min} - {x_axis_max}",
#                             "Number of Samples": num_samples,
#                             "Mean": mean_value_au,
#                             "Expected Value": data_subset[expected_val_col].mean(),
#                             "Standard Deviation": standard_deviation,
#                             "Number of Outliers": num_outliers,
#                             "Bias (%)": bias,
#                             "Failure Rate (%)": percentage_outliers,
#                             'Upper Limit': data_subset[upperlimit_col].mean(),
#                             'Lower Limit': data_subset[lowerlimit_col].mean(),
#                             'Source': data_subset[source_col].iloc[0]
#                         }
#                         # ← insert this block now:
#                         if isinstance(grp_values, tuple):
#                             for field, val in zip(group_fields, grp_values):
#                                 summary_data2[field] = val
#                         else:
#                             summary_data2[group_fields[0]] = grp_values
                    
#                     # --- Determine chart unit from filtered data
#                     if unit_col_name is not None:
#                         unique_units = data_subset[unit_col_name].unique()
#                         chart_unit = unique_units[0] if len(unique_units) else ""
#                     else:
#                         chart_unit = custom_unit if (unit_selection == "Custom") else unit
#                     summary_data2['Unit'] = chart_unit

#                     summary_data_rounded2 = {k: round(v, 2) if isinstance(v, (int, float)) else v for k, v in summary_data2.items()}
#                     if group_fields:
#                         ordered_keys = list(group_fields) + [k for k in summary_data_rounded2 if k not in group_fields]
#                         summary_data_rounded2 = {k: summary_data_rounded2[k] for k in ordered_keys}
#                     #### One Decimal for Bias and Failure Rate 
#                     summary_data_rounded2['Bias (%)'] = round(summary_data_rounded2['Bias (%)'], 1)
#                     summary_data_rounded2['Failure Rate (%)'] = round(
#                     summary_data_rounded2['Failure Rate (%)'], 1
#                                                                                     )
#                     #### One Decimal for Bias and Failure Rate End

#                     allstats.append(pd.DataFrame([summary_data_rounded2]))
#                     st.dataframe(pd.DataFrame([summary_data_rounded2]))
#                     summary_x_position = 0.99
#                     summary_y_position = 0.02
#                     # skip empty groups
#                     if data_subset.empty:
#                         st.warning(f"No data for group {group_label} – skipping.")
#                         continue

#                     # fix NaN/Inf y-limits
#                     if not (np.isfinite(y_axis_min) and np.isfinite(y_axis_max)):
#                         y_axis_min = data_subset[grade_col].min()
#                         y_axis_max = data_subset[grade_col].max()

#                     fig, ax = plt.subplots(figsize=(15, 8), dpi=500)
#                     ax.scatter(data_subset['Sequence'], data_subset[grade_col], label=f'{elem}', color=Point_color, edgecolors=Point_color, s=30, marker='o')
#                     mask_exceed_limits = ((data_subset[grade_col] > data_subset['Upper Bound (3SD)']) | (data_subset[grade_col] < data_subset['Lower Bound (3SD)']))
#                     ax.plot(data_subset['Sequence'], data_subset[expected_val_col], label='Expected Value', color='black', linestyle='--', linewidth=1.5)
#                     ax.scatter(data_subset['Sequence'][mask_exceed_limits], data_subset[grade_col][mask_exceed_limits], color=failure_color, edgecolors='#A36F67', s=30, marker='o', label='Failures')
#                     ax.axhline(y=mean_value_au, color='#92B2F5', linestyle='-', label='Mean', linewidth=1.75)
#                     if not UseUL_LW:
#                         ax.plot(data_subset['Sequence'], data_subset['Upper Bound (2SD)'], label='+2 SD', color=twoSD_color, linestyle='-', linewidth=1.75)
#                         ax.plot(data_subset['Sequence'], data_subset['Lower Bound (2SD)'], label='-2 SD', color=twoSD_color, linestyle='-', linewidth=1.75)
#                         ax.plot(data_subset['Sequence'], data_subset['Upper Bound (3SD)'], label='+3 SD', color=threeSD_color, linestyle='-', linewidth=1.75)
#                         ax.plot(data_subset['Sequence'], data_subset['Lower Bound (3SD)'], label='-3 SD', color=threeSD_color, linestyle='-', linewidth=1.75)
#                     else:
#                         ax.plot(data_subset['Sequence'], data_subset['Upper Bound (3SD)'], label='Upper Limit', color=threeSD_color, linestyle='-', linewidth=1.75)
#                         ax.plot(data_subset['Sequence'], data_subset['Lower Bound (3SD)'], label='Lower Limit', color=threeSD_color, linestyle='-', linewidth=1.75)
#                     data_subset['Moving Mean'] = data_subset[grade_col].rolling(window=7).mean()
#                     ax.plot(data_subset['Sequence'], data_subset['Moving Mean'], label='Moving Mean (7)', color='#A6A6A6', linestyle='--', linewidth=0.75)
#                     ax.set_xlabel('Date')
#                     ax.set_ylabel(f'{elem} {chart_unit}', fontsize=15)
#                     title_text = f'{certificate} - {elem} {chart_unit}'
#                     if group_label:
#                         title_text += f' - {group_label}'
#                     if labname:
#                         title_text += f' - {labname}'
#                     ax.set_title(title_text, fontsize=20)
#                     ax.grid(False)
#                     ax.legend(loc='upper right', bbox_to_anchor=(1, 1), fancybox=True, shadow=True)
#                     ax.set_ylim(bottom=y_axis_min, top=y_axis_max)
#                     ax.set_xticks(range(len(data_subset['Sequence'].cat.categories)))
#                     ax.set_xticklabels(data_subset[date_col].dt.strftime('%Y-%m-%d'), rotation=x_text_rotation)
#                     ax.margins(x=x_margin)
#                     plt.xticks(rotation=x_text_rotation, ha='right')
#                     tick_interval = max(1, len(data_subset) // nbin)
#                     ax.xaxis.set_major_locator(MultipleLocator(tick_interval))
#                     if show_summary:
#                         summary_text = "\n".join([f"{k}: {v}" for k, v in summary_data_rounded.items()])
#                         ax.text(summary_x_position, summary_y_position, summary_text, transform=ax.transAxes, verticalalignment='bottom', horizontalalignment='right', bbox=dict(facecolor='white', edgecolor='black', boxstyle='round,pad=0.5'))
#                     ax.text(0.01, 0.02, slr_text, transform=ax.transAxes, fontsize=8, color='gray', verticalalignment='bottom', horizontalalignment='left')
#                     plt.tight_layout()
#                     fig_list.append(fig)
#                     st.pyplot(fig)
#             else:
#                 # If no grouping fields are selected, process the entire filtered_data
#                 data_subset = filtered_data.copy()
#                 group_label = ""
#                 group_key = f"{unique_key_prefix}_all"
#                 x_axis_min = st.date_input("X axis min", key=f"x_min_{group_key}", value=data_subset[date_col].min())
#                 x_axis_max = st.date_input("X axis max", key=f"x_max_{group_key}", value=data_subset[date_col].max())
#                 y_axis_min = st.number_input('Y min', key=f"y_min_{group_key}", value=data_subset[grade_col].min() - data_subset[grade_col].std())
#                 y_axis_max = st.number_input('Y max', key=f"y_max_{group_key}", value=data_subset[grade_col].max() + data_subset[grade_col].std())
#                 labname = st.text_input('Lab Name', key=f"lab_{group_key}")
#                 if not UseUL_LW:
#                     if not usemean:
#                         expected_val = data_subset[expected_val_col].mean()
#                         mean_value_au = data_subset[grade_col].mean()
#                         if not sdcalc:
#                             standard_deviation = data_subset[grade_col].std()
#                             data_subset['Upper Bound (2SD)'] = expected_val + (twostd * standard_deviation)
#                             data_subset['Lower Bound (2SD)'] = expected_val - (twostd * standard_deviation)
#                             data_subset['Upper Bound (3SD)'] = expected_val + (threestd * standard_deviation)
#                             data_subset['Lower Bound (3SD)'] = expected_val - (threestd * standard_deviation)
#                         else:
#                             if len(data_subset[std_col].unique()) == 1:
#                                 standard_deviation = data_subset[std_col].unique()[0]
#                                 data_subset['Upper Bound (2SD)'] = expected_val + (twostd * standard_deviation)
#                                 data_subset['Lower Bound (2SD)'] = expected_val - (twostd * standard_deviation)
#                                 data_subset['Upper Bound (3SD)'] = expected_val + (threestd * standard_deviation)
#                                 data_subset['Lower Bound (3SD)'] = expected_val - (threestd * standard_deviation)
#                             else:
#                                 st.warning('There are multiple values in the STD column; please check the file for any errors')
#                     else:
#                         expected_val = data_subset[expected_val_col].mean()
#                         mean_value_au = data_subset[grade_col].mean()
#                         if not sdcalc:
#                             standard_deviation = data_subset[grade_col].std()
#                             data_subset['Upper Bound (2SD)'] = mean_value_au + (twostd * standard_deviation)
#                             data_subset['Lower Bound (2SD)'] = mean_value_au - (twostd * standard_deviation)
#                             data_subset['Upper Bound (3SD)'] = mean_value_au + (threestd * standard_deviation)
#                             data_subset['Lower Bound (3SD)'] = mean_value_au - (threestd * standard_deviation)
#                         else:
#                             if len(data_subset[std_col].unique()) == 1:
#                                 standard_deviation = data_subset[std_col].unique()[0]
#                                 data_subset['Upper Bound (2SD)'] = mean_value_au + (twostd * standard_deviation)
#                                 data_subset['Lower Bound (2SD)'] = mean_value_au - (twostd * standard_deviation)
#                                 data_subset['Upper Bound (3SD)'] = mean_value_au + (threestd * standard_deviation)
#                                 data_subset['Lower Bound (3SD)'] = mean_value_au - (threestd * standard_deviation)
#                             else:
#                                 st.warning('There are multiple values in the STD column; please check the file for any errors')
#                 else:
#                     expected_val = data_subset[expected_val_col].mean()
#                     mean_value_au = data_subset[grade_col].mean()
#                     standard_deviation = data_subset[grade_col].std()
#                     data_subset['Upper Bound (3SD)'] = data_subset[upperlimit_col].mean()
#                     data_subset['Lower Bound (3SD)'] = data_subset[lowerlimit_col].mean()
#                 data_subset = data_subset.sort_values(by=[date_col]).reset_index(drop=True)
#                 x_axis_min_dt = pd.to_datetime(x_axis_min)
#                 x_axis_max_dt = pd.to_datetime(x_axis_max) + pd.Timedelta(days=1)
#                 if x_axis_max_dt > x_axis_min_dt:
#                     data_subset = data_subset[(data_subset[date_col] >= x_axis_min_dt) & (data_subset[date_col] <= x_axis_max_dt)]
#                 elif x_axis_max_dt == x_axis_min_dt:
#                     data_subset = data_subset[data_subset[date_col].dt.date == x_axis_min]
#                 else:
#                     st.write('There is a problem with dates')
#                 data_subset['Sequence'] = range(0, len(data_subset))
#                 st.dataframe(data_subset)
#                 nbin = st.slider('Number of Ticks', 1, len(data_subset)-1, 3, key=f"nbin_{group_key}")
#                 data_subset['Sequence'] = data_subset['Sequence'].astype('category')
#                 num_samples = len(data_subset[grade_col])
#                 num_outliers = sum((data_subset[grade_col] > data_subset['Upper Bound (3SD)']) | (data_subset[grade_col] < data_subset['Lower Bound (3SD)']))
#                 bias = ((mean_value_au / data_subset[expected_val_col].iloc[0]) - 1) * 100
#                 percentage_outliers = (num_outliers / num_samples) * 100
#                 summary_data = {
#                     "Number of Samples": num_samples,
#                     "Mean": mean_value_au,
#                     "Expected Value": data_subset[expected_val_col].mean(),
#                     "Standard Deviation": standard_deviation,
#                     "Number of Outliers": num_outliers,
#                     "Bias (%)": bias,
#                     "Failure Rate (%)": percentage_outliers
#                 }
#                 summary_data_rounded = {k: round(v, 2) for k, v in summary_data.items()}
#                 if not UseUL_LW:
#                     summary_data2 = {
#                         'Element': elem,
#                         'Unit': None,  # will be set below
#                         'CRM': certificate,
#                         'Periode Range': f"{x_axis_min} - {x_axis_max}",
#                         "Number of Samples": num_samples,
#                         "Mean": mean_value_au,
#                         "Expected Value": data_subset[expected_val_col].mean(),
#                         "Standard Deviation": standard_deviation,
#                         "Number of Outliers": num_outliers,
#                         "Bias (%)": bias,
#                         "Failure Rate (%)": percentage_outliers,
#                         "Upper Bound (2SD)": mean_value_au + (twostd * standard_deviation),
#                         "Lower Bound (2SD)": mean_value_au - (twostd * standard_deviation),
#                         'Upper Bound (3SD)': mean_value_au + (threestd * standard_deviation),
#                         'Lower Bound (3SD)': mean_value_au - (threestd * standard_deviation)
#                     }
#                     # ← insert this block now:
#                     if isinstance(grp_values, tuple):
#                         for field, val in zip(group_fields, grp_values):
#                             summary_data2[field] = val
#                     else:
#                         summary_data2[group_fields[0]] = grp_values
#                 else:
#                     summary_data2 = {
#                         'Element': elem,
#                         'Unit': None,  # will be set below
#                         'CRM': certificate,
#                         'Periode Range': f"{x_axis_min} - {x_axis_max}",
#                         "Number of Samples": num_samples,
#                         "Mean": mean_value_au,
#                         "Expected Value": data_subset[expected_val_col].mean(),
#                         "Standard Deviation": standard_deviation,
#                         "Number of Outliers": num_outliers,
#                         "Bias (%)": bias,
#                         "Failure Rate (%)": percentage_outliers,
#                         'Upper Limit': data_subset[upperlimit_col].mean(),
#                         'Lower Limit': data_subset[lowerlimit_col].mean(),
#                         'Source': data_subset[source_col].iloc[0]
#                     }
#                     # ← insert this block now:
#                     if isinstance(grp_values, tuple):
#                         for field, val in zip(group_fields, grp_values):
#                             summary_data2[field] = val
#                     else:
#                         summary_data2[group_fields[0]] = grp_values
#                 if unit_col_name is not None:
#                     unique_units = data_subset[unit_col_name].unique()
#                     chart_unit = unique_units[0] if len(unique_units) else ""
#                 else:
#                     chart_unit = custom_unit if (unit_selection == "Custom") else unit
#                 summary_data2['Unit'] = chart_unit

#                 summary_data_rounded2 = {k: round(v, 2) if isinstance(v, (int, float)) else v for k, v in summary_data2.items()}
#                 if group_fields:
#                     ordered_keys = list(group_fields) + [k for k in summary_data_rounded2 if k not in group_fields]
#                     summary_data_rounded2 = {k: summary_data_rounded2[k] for k in ordered_keys}
#                                 #### One Decimal for Bias and Failure Rate 
#                 summary_data_rounded2['Bias (%)'] = round(summary_data_rounded2['Bias (%)'], 1)
#                 summary_data_rounded2['Failure Rate (%)'] = round(
#                 summary_data_rounded2['Failure Rate (%)'], 1
#                                                                                     )
#                 #### One Decimal for Bias and Failure Rate End
#                 allstats.append(pd.DataFrame([summary_data_rounded2]))
#                 st.dataframe(pd.DataFrame([summary_data_rounded2]))
#                 summary_x_position = 0.99
#                 summary_y_position = 0.02

#                 #### Fxing error 
#                 if data_subset.empty:
#                     st.warning("No data to plot for those filters – skipping chart.")
#                     continue

#                 # ensure your y-limits aren’t NaN
#                 if not (np.isfinite(y_axis_min) and np.isfinite(y_axis_max)):
#                     y_axis_min = data_subset[grade_col].min()
#                     y_axis_max = data_subset[grade_col].max()

#                 #### Fixing error end
#                 fig, ax = plt.subplots(figsize=(15, 8), dpi=500)
#                 ax.scatter(data_subset['Sequence'], data_subset[grade_col], label=f'{elem}', color='black', edgecolors='black', s=30, marker='o')
#                 mask_exceed_limits = ((data_subset[grade_col] > data_subset['Upper Bound (3SD)']) | (data_subset[grade_col] < data_subset['Lower Bound (3SD)']))
#                 ax.plot(data_subset['Sequence'], data_subset[expected_val_col], label='Expected Value', color='black', linestyle='--', linewidth=1.5)
#                 ax.scatter(data_subset['Sequence'][mask_exceed_limits], data_subset[grade_col][mask_exceed_limits], color=failure_color, edgecolors='#A36F67', s=30, marker='o', label='Failures')
#                 ax.axhline(y=mean_value_au, color='#92B2F5', linestyle='-', label='Mean', linewidth=1.75)
#                 if not UseUL_LW:
#                     ax.plot(data_subset['Sequence'], data_subset['Upper Bound (2SD)'], label='+2 SD', color=twoSD_color, linestyle='-', linewidth=1.75)
#                     ax.plot(data_subset['Sequence'], data_subset['Lower Bound (2SD)'], label='-2 SD', color=twoSD_color, linestyle='-', linewidth=1.75)
#                     ax.plot(data_subset['Sequence'], data_subset['Upper Bound (3SD)'], label='+3 SD', color=threeSD_color, linestyle='-', linewidth=1.75)
#                     ax.plot(data_subset['Sequence'], data_subset['Lower Bound (3SD)'], label='-3 SD', color=threeSD_color, linestyle='-', linewidth=1.75)
#                 else:
#                     ax.plot(data_subset['Sequence'], data_subset['Upper Bound (3SD)'], label='Upper Limit', color=threeSD_color, linestyle='-', linewidth=1.75)
#                     ax.plot(data_subset['Sequence'], data_subset['Lower Bound (3SD)'], label='Lower Limit', color=threeSD_color, linestyle='-', linewidth=1.75)
#                 data_subset['Moving Mean'] = data_subset[grade_col].rolling(window=7).mean()
#                 ax.plot(data_subset['Sequence'], data_subset['Moving Mean'], label='Moving Mean (7)', color='#A6A6A6', linestyle='--', linewidth=0.75)
#                 ax.set_xlabel('Date')
#                 ax.set_ylabel(f'{elem} {chart_unit}', fontsize=15)
#                 title_text = f'{certificate} - {elem} {chart_unit}'
#                 if group_label:
#                     title_text += f' - {group_label}'
#                 if labname:
#                     title_text += f' - {labname}'
#                 ax.set_title(title_text, fontsize=20)
#                 ax.grid(False)
#                 ax.legend(loc='upper right', bbox_to_anchor=(1, 1), fancybox=True, shadow=True)
#                 ax.set_ylim(bottom=y_axis_min, top=y_axis_max)
#                 ax.set_xticks(range(len(data_subset['Sequence'].cat.categories)))
#                 ax.set_xticklabels(data_subset[date_col].dt.strftime('%Y-%m-%d'), rotation=x_text_rotation)
#                 ax.margins(x=x_margin)
#                 plt.xticks(rotation=x_text_rotation, ha='right')
#                 tick_interval = max(1, len(data_subset) // nbin)
#                 ax.xaxis.set_major_locator(MultipleLocator(tick_interval))
#                 if show_summary:
#                     summary_text = "\n".join([f"{k}: {v}" for k, v in summary_data_rounded.items()])
#                     ax.text(summary_x_position, summary_y_position, summary_text, transform=ax.transAxes, verticalalignment='bottom', horizontalalignment='right', bbox=dict(facecolor='white', edgecolor='black', boxstyle='round,pad=0.5'))
#                 ax.text(0.01, 0.02, slr_text, transform=ax.transAxes, fontsize=8, color='gray', verticalalignment='bottom', horizontalalignment='left')
#                 plt.tight_layout()
#                 fig_list.append(fig)
#                 st.pyplot(fig)
#     try:
#         combined_stats = pd.concat(allstats, ignore_index=True)
#         st.dataframe(combined_stats)
#         # --- Download button for combined summary table ---
#         csv = combined_stats.to_csv(index=False).encode('utf-8')
#         st.download_button("Download Combined Summary Table", data=csv, file_name="combined_summary.csv", mime="text/csv")
#     except:
#         pass
#     if st.button('Generate Presentation'):
#         presentation_path = save_fig_to_presentation(fig_list)
#         st.success(f"Presentation generated! [Download]({presentation_path})")
        
# session_state_dict = serialize_session_state(st.session_state)
# session_state_json = json.dumps(session_state_dict)
# st.download_button('Save Progress', data=session_state_json, file_name='saved_progress.json', mime='application/json')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import streamlit as st
import datetime
import random
from pptx import Presentation
from pptx.util import Inches
import io
import numpy as np
from matplotlib.ticker import MaxNLocator, MultipleLocator
import matplotlib.colors as mcolors
import json
from pyrpa.UI import common

# ------------------------------------------------------------------
#                      HELPER FUNCTIONS
# ------------------------------------------------------------------
def remove_placeholders_from_slide(slide):
    for shape in slide.shapes:
        if not shape.is_placeholder:
            continue
        sp = shape._element
        sp.getparent().remove(sp)

def build_presentation_bytes(fig_list):
    """Build the slide deck entirely in memory and return the .pptx bytes.

    Previously this wrote the deck to a file on the server and handed the user
    a relative markdown link (`[Download](charts_presentation.pptx)`). On a
    hosted deploy that link is a navigation, not a download — clicking it
    reloaded the app into a fresh session and bounced the user back to the
    Home/passphrase screen, and the file never reached their computer. Serving
    the bytes through st.download_button (see call site) fixes both.
    """
    prs = Presentation()
    for fig in fig_list:
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        remove_placeholders_from_slide(slide)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')

        # centre image on slide
        available_width  = prs.slide_width
        available_height = prs.slide_height
        buf.seek(0)
        tmp_pic = slide.shapes.add_picture(buf, 0, 0, width=available_width)
        image_aspect_ratio = tmp_pic.width / tmp_pic.height
        slide_aspect_ratio = available_width / available_height
        if image_aspect_ratio > slide_aspect_ratio:
            final_width  = available_width
            final_height = int(final_width / image_aspect_ratio)
        else:
            final_height = available_height
            final_width  = int(final_height * image_aspect_ratio)
        left = (available_width  - final_width)  / 2
        top  = (available_height - final_height) / 2
        slide.shapes._spTree.remove(tmp_pic._element)
        buf.seek(0)
        slide.shapes.add_picture(buf, left, top,
                                 width=final_width, height=final_height)
        buf.close()
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()

def serialize_session_state(state):
    """Build a JSON-serialisable snapshot of session state.

    Only values that can round-trip through JSON are kept. Anything else —
    the generated PPTX bytes in `crm_ppt_bytes`, DataFrames, uploaded-file
    handles, numpy scalars/arrays that don't coerce — is dropped. Previously
    every value was passed straight to `json.dumps` at the call site, so the
    first non-serialisable entry (e.g. after clicking Generate Presentation)
    raised a TypeError that ran *before* the 'Save Progress' download button
    and stopped it from ever rendering.
    """
    serialized_state = {}
    for key, value in state.items():
        if isinstance(value, (datetime.date, datetime.datetime)):
            serialized_state[key] = value.isoformat()
            continue
        if isinstance(value, np.generic):      # numpy scalar -> python scalar
            value = value.item()
        elif isinstance(value, np.ndarray):    # numpy array -> list
            value = value.tolist()
        try:
            json.dumps(value)                   # keep only what JSON accepts
        except (TypeError, ValueError):
            continue
        serialized_state[key] = value
    return serialized_state

def deserialize_session_state(state_dict):
    deserialized_state = {}
    for key, value in state_dict.items():
        if isinstance(value, str):
            try:
                deserialized_state[key] = datetime.date.fromisoformat(value)
            except ValueError:
                deserialized_state[key] = value
        else:
            deserialized_state[key] = value
    return deserialized_state

def _idx_or(col, col_list, fallback=0):
    """Return the index of *col* in col_list, or fallback if col is None/absent."""
    return col_list.index(col) if col in col_list else fallback

# ------------------------------------------------------------------
#                        APP LAYOUT
# ------------------------------------------------------------------
st.set_page_config(layout="wide")

saved_progress_file = st.sidebar.file_uploader("Load Progress", type=['json'])
if common.load_saved_state(saved_progress_file, key="crms", transform=deserialize_session_state):
    st.success("Progress loaded!")
    st.info("Please upload the same data file used in the saved progress.")

file = st.sidebar.file_uploader("Choose a data file (CSV or Excel)", ["csv","xlsx","xls"])
if file is not None:
    _crms_field_map = {
        "date_col": "date", "grade_col": "value", "CRM_col": "crm", "elementcolumn": "element",
        "expected_val_col": "expected", "source_col": "project",
        "optional_group_field_1": "lab", "unit_col_sel": "unit",
    }
    data     = common.read_data_file(file)
    data     = common.offer_wide_reshape(data, key="crms")
    common.sync_column_mapping(data, key="crms", field_map=_crms_field_map)
    columns  = list(data.columns)                # for auto-complete / filters

    # ---------------------- SIDEBAR SETTINGS ----------------------
    _guess = common.auto_map_columns(columns, ["date","value","crm","element","expected","project","lab","unit"])
    date_idx      = _idx_or(_guess["date"], columns)
    grade_idx     = _idx_or(_guess["value"], columns)
    crm_idx       = _idx_or(_guess["crm"], columns)
    elements_idx  = _idx_or(_guess["element"], columns)
    expected_idx  = _idx_or(_guess["expected"], columns)

    date_col      = st.sidebar.selectbox('Date Column', columns, index=date_idx, key='date_col')
    data[date_col] = pd.to_datetime(data[date_col])

    grade_col     = st.sidebar.selectbox('Grade Column', columns, index=grade_idx, key='grade_col')
    CRM_col       = st.sidebar.selectbox('CRM Column',   columns, index=crm_idx,  key='CRM_col')
    elementcolumn = st.sidebar.selectbox('Element Column', columns, index=elements_idx, key='elementcolumn')
    expected_val_col = st.sidebar.selectbox('Expected Value Column', columns, index=expected_idx, key='expected_val_col')
    project_idx   = _idx_or(_guess["project"], columns)
    source_col    = st.sidebar.selectbox('Project', columns, index=project_idx, key='source_col')

    # convert grades to float (with quick feedback)
    try:
        data[grade_col] = data[grade_col].astype(float)
    except Exception:
        st.error('Make sure to choose the right grade column')

    elements = st.multiselect('Select Element', data[elementcolumn].unique(), key='element')

    # ---------------- OPTIONAL GROUPING FIELDS (unchanged) -------
    lab_idx = _idx_or(_guess["lab"] or "None", ['None'] + columns)
    optional_group_field_1 = st.sidebar.selectbox('Lab',
                                                  ['None'] + columns,
                                                  index=lab_idx,
                                                  key='optional_group_field_1')
    optional_group_field_2 = st.sidebar.selectbox('Optional Grouping Field 2',
                                                  ['None'] + columns,
                                                  key='optional_group_field_2')
    optional_group_field_3 = st.sidebar.selectbox('Optional Grouping Field 3',
                                                  ['None'] + columns,
                                                  key='optional_group_field_3')

    # ---------------- UNIT (trackable, auto-detected from header) -----------------
    # Units can vary across methods/standards, so read them from a data column when
    # available rather than from a fixed predefined list. Falls back to free text.
    unit_idx = _idx_or(_guess["unit"] or "None", ['None'] + columns)
    unit_col_sel = st.sidebar.selectbox('Unit Column', ['None'] + columns,
                                        index=unit_idx, key='unit_col_sel')
    custom_unit = st.sidebar.text_input("Custom Unit (used if no Unit column selected)",
                                        value="", key="custom_unit")
    if unit_col_sel != 'None':
        unit_col_name  = unit_col_sel       # unit is read per-chart from this column
        unit           = None
        unit_selection = None
    else:
        unit_col_name  = None
        unit           = custom_unit
        unit_selection = "Custom"

    # ----------------------- STYLE OPTIONS ------------------------
    slr_text       = st.sidebar.text_input("SLR Text",
                                           value=f"SLR {datetime.datetime.now().year}",
                                           key="slr_text")
    col1, col2, col3, col4, col5 = st.columns(5)
    Point_color   = col1.color_picker('Sample Color', '#7FA37F', key='Point_color')
    failure_color = col2.color_picker('Failure Color', '#FF0000', key='failure_color')
    twoSD_color   = col3.color_picker('2 SD Color', '#B5ED38', key='twoSD_color')
    threeSD_color = col4.color_picker('3 SD Color', '#7FA37F', key='threeSD_color')
    show_summary  = col5.checkbox('Show Summary', key='show_summary')
    with st.sidebar.expander("🎨 Markers and line colours"):
        sample_marker  = common.marker_select('Sample marker', key='crms_sample_marker')
        failure_marker = common.marker_select('Failure marker', key='crms_failure_marker')
        expected_color = st.color_picker('Expected value line', '#000000', key='crms_expected_color')
        mean_color     = st.color_picker('Mean line', '#92B2F5', key='crms_mean_color')
        movmean_color  = st.color_picker('Moving mean line', '#A6A6A6', key='crms_movmean_color')
    crm_date_opts = common.date_display_options('crms', data[date_col])

    sdcalc  = st.sidebar.checkbox('Expected Value + 1SD', key='sdcalc',
                                  help='Use this Failure Criteria based on the CRM certificate Expected Value and 1SD')
    usemean = st.sidebar.checkbox('Mean value + 1SD', key='usemean',
                                  help='Use this Failure Criteria based on the data mean and calculated SD')
    UseUL_LW = st.sidebar.checkbox('Use an upper/lower limits fields', key='UseUL_LW')
    if not UseUL_LW:
        if not sdcalc:
            twostd  = st.sidebar.number_input('1st SD Threshold', value=2, key='twostd')
            threestd = st.sidebar.number_input('2nd SD Threshold', value=3, key='threestd')
        else:
            std_col = st.sidebar.selectbox('SD Column', columns, key='std_col')
            twostd  = st.sidebar.number_input('1st SD Threshold', value=2, key='twostd')
            threestd = st.sidebar.number_input('2nd SD Threshold', value=3, key='threestd')
    else:
        upperlimit_col = st.sidebar.selectbox('Upper Limit Column', columns, key='upperlimit_col')
        lowerlimit_col = st.sidebar.selectbox('Lower Limit Column', columns, key='lowerlimit_col')

    fig_list  = []
    allstats  = []
    x_text_rotation = st.sidebar.number_input('X Axis text rotation', value=0, key='x_text_rotation')
    x_margin        = st.sidebar.number_input('X axis margin', value=0.00, step=0.01, key='x_margin')
    fig_size        = common.aspect_ratio_input((15, 8), key='crm_aspect', container=st.sidebar)

    # ------------------------------------------------------------------
    #                      MAIN PLOTTING LOOP
    # ------------------------------------------------------------------
    for i, elem in enumerate(elements):
        filtered = data[data[elementcolumn] == elem]
        prefix   = f"{i}_{elem}"

        # 1️⃣  CRM selector
        selected_crms = st.multiselect('Select CRMs',
                                       filtered[CRM_col].unique(),
                                       key=f"CRM_{prefix}")
        if not selected_crms:
            selected_crms = list(filtered[CRM_col].unique())
        filtered = filtered[filtered[CRM_col].isin(selected_crms)]

        # 2️⃣  🔥 NEW OPTIONAL FILTERS (side-by-side)  ------------------
        fc1, fc2 = st.columns(2)

        with fc1:
            f1_col = st.selectbox('Filter Column 1',
                                  ['None'] + columns,
                                  key=f"f1_col_{prefix}")
            if f1_col != 'None':
                f1_vals = st.multiselect('Values 1',
                                         sorted(filtered[f1_col].dropna().unique()),
                                         key=f"f1_vals_{prefix}")
            else:
                f1_vals = []
        with fc2:
            f2_col = st.selectbox('Filter Column 2',
                                  ['None'] + columns,
                                  key=f"f2_col_{prefix}")
            if f2_col != 'None':
                f2_vals = st.multiselect('Values 2',
                                         sorted(filtered[f2_col].dropna().unique()),
                                         key=f"f2_vals_{prefix}")
            else:
                f2_vals = []

        if f1_col != 'None' and f1_vals:
            filtered = filtered[filtered[f1_col].isin(f1_vals)]
        if f2_col != 'None' and f2_vals:
            filtered = filtered[filtered[f2_col].isin(f2_vals)]
        # --------------------------------------------------------------

        st.markdown(f"<h1 style='text-align: center; color: #7FA37F;'>Charts for {elem}</h1>",
                    unsafe_allow_html=True)

        # ------------------------------------------------------------------
        #        ----- REST OF ORIGINAL PLOTTING / STATS CODE -----
        # ------------------------------------------------------------------
        # (Everything from "for j, certificate in enumerate(filtered[CRM_col].unique()):"
        #  down to the final Save Progress button remains exactly the same.)
        for j, certificate in enumerate(filtered[CRM_col].unique()):
            unique_key_prefix = f"{i}_{j}_{elem}_{certificate}"
            min_grade_threshold = st.number_input('Min grade threshold',
                                                  value=filtered[grade_col].min(),
                                                  key=f"min_{unique_key_prefix}")
            max_grade_threshold = st.number_input('Max grade threshold',
                                                  value=filtered[grade_col].max(),
                                                  key=f"max_{unique_key_prefix}")

            filtered_data = filtered[(filtered[grade_col] >= min_grade_threshold) &
                                     (filtered[grade_col] <= max_grade_threshold) &
                                     (filtered[CRM_col] == certificate)]

            # --- Combine optional grouping fields ---
            group_fields = []
            if optional_group_field_1 != 'None':
                group_fields.append(optional_group_field_1)
            if optional_group_field_2 != 'None':
                group_fields.append(optional_group_field_2)
            if optional_group_field_3 != 'None':
                group_fields.append(optional_group_field_3)

            if group_fields:
                grouped = filtered_data.groupby(group_fields)
                for grp_values, group_data in grouped:
                    data_subset = group_data.copy()
                    if isinstance(grp_values, tuple):
                        group_label = " - ".join([str(val) for val in grp_values])
                    else:
                        group_label = str(grp_values)
                    group_key = f"{unique_key_prefix}_{group_label}"

                    x_axis_min = st.date_input("X axis min",
                                               key=f"x_min_{group_key}",
                                               value=data_subset[date_col].min())
                    x_axis_max = st.date_input("X axis max",
                                               key=f"x_max_{group_key}",
                                               value=data_subset[date_col].max())
                    y_axis_min = st.number_input('Y min',
                                                 key=f"y_min_{group_key}",
                                                 value=data_subset[grade_col].min() - data_subset[grade_col].std())
                    y_axis_max = st.number_input('Y max',
                                                 key=f"y_max_{group_key}",
                                                 value=data_subset[grade_col].max() + data_subset[grade_col].std())
                    labname = st.text_input('Lab Name', key=f"lab_{group_key}")

                    # ------------------------------------------------------------------
                    #               >>> ORIGINAL CALC / PLOT BLOCK <<<
                    # ------------------------------------------------------------------
                    if not UseUL_LW:
                        if not usemean:
                            expected_val = data_subset[expected_val_col].mean()
                            mean_value_au = data_subset[grade_col].mean()
                            if not sdcalc:
                                standard_deviation = data_subset[grade_col].std()
                                data_subset['Upper Bound (2SD)'] = expected_val + (twostd * standard_deviation)
                                data_subset['Lower Bound (2SD)'] = expected_val - (twostd * standard_deviation)
                                data_subset['Upper Bound (3SD)'] = expected_val + (threestd * standard_deviation)
                                data_subset['Lower Bound (3SD)'] = expected_val - (threestd * standard_deviation)
                            else:
                                if len(data_subset[std_col].unique()) == 1:
                                    standard_deviation = data_subset[std_col].unique()[0]
                                    data_subset['Upper Bound (2SD)'] = expected_val + (twostd * standard_deviation)
                                    data_subset['Lower Bound (2SD)'] = expected_val - (twostd * standard_deviation)
                                    data_subset['Upper Bound (3SD)'] = expected_val + (threestd * standard_deviation)
                                    data_subset['Lower Bound (3SD)'] = expected_val - (threestd * standard_deviation)
                                else:
                                    st.warning('There are multiple values in the STD column; please check the file for any errors')
                        else:
                            expected_val = data_subset[expected_val_col].mean()
                            mean_value_au = data_subset[grade_col].mean()
                            if not sdcalc:
                                standard_deviation = data_subset[grade_col].std()
                                data_subset['Upper Bound (2SD)'] = mean_value_au + (twostd * standard_deviation)
                                data_subset['Lower Bound (2SD)'] = mean_value_au - (twostd * standard_deviation)
                                data_subset['Upper Bound (3SD)'] = mean_value_au + (threestd * standard_deviation)
                                data_subset['Lower Bound (3SD)'] = mean_value_au - (threestd * standard_deviation)
                            else:
                                if len(data_subset[std_col].unique()) == 1:
                                    standard_deviation = data_subset[std_col].unique()[0]
                                    data_subset['Upper Bound (2SD)'] = mean_value_au + (twostd * standard_deviation)
                                    data_subset['Lower Bound (2SD)'] = mean_value_au - (twostd * standard_deviation)
                                    data_subset['Upper Bound (3SD)'] = mean_value_au + (threestd * standard_deviation)
                                    data_subset['Lower Bound (3SD)'] = mean_value_au - (threestd * standard_deviation)
                                else:
                                    st.warning('There are multiple values in the STD column; please check the file for any errors')
                    else:
                        expected_val = data_subset[expected_val_col].mean()
                        mean_value_au = data_subset[grade_col].mean()
                        standard_deviation = data_subset[grade_col].std()
                        data_subset['Upper Bound (3SD)'] = data_subset[upperlimit_col].mean()
                        data_subset['Lower Bound (3SD)'] = data_subset[lowerlimit_col].mean()

                    data_subset = data_subset.sort_values(by=[date_col]).reset_index(drop=True)

                    x_axis_min_dt = pd.to_datetime(x_axis_min)
                    x_axis_max_dt = pd.to_datetime(x_axis_max) + pd.Timedelta(days=1)
                    if x_axis_max_dt > x_axis_min_dt:
                        data_subset = data_subset[(data_subset[date_col] >= x_axis_min_dt) &
                                                  (data_subset[date_col] <= x_axis_max_dt)]
                    elif x_axis_max_dt == x_axis_min_dt:
                        data_subset = data_subset[data_subset[date_col].dt.date == x_axis_min]
                    else:
                        st.write('There is a problem with dates')
                    data_subset = common.filter_dates(data_subset, date_col, crm_date_opts).reset_index(drop=True)
                    if data_subset.empty:
                        st.warning(f"No data in the dates shown for {certificate} {group_label} – skipping.")
                        continue

                    data_subset['Sequence'] = range(0, len(data_subset))
                    st.dataframe(data_subset)

                    nbin = st.slider('Number of Ticks', 1, max(1, len(data_subset)-1), 3,
                                     key=f"nbin_{group_key}")
                    data_subset['Sequence'] = data_subset['Sequence'].astype('category')

                    num_samples  = len(data_subset[grade_col])
                    num_outliers = sum((data_subset[grade_col] > data_subset['Upper Bound (3SD)']) |
                                       (data_subset[grade_col] < data_subset['Lower Bound (3SD)']))
                    bias = ((mean_value_au / data_subset[expected_val_col].iloc[0]) - 1) * 100
                    percentage_outliers = (num_outliers / num_samples) * 100

                    summary_data = {
                        "Number of Samples": num_samples,
                        "Mean": mean_value_au,
                        "Expected Value": data_subset[expected_val_col].mean(),
                        "Standard Deviation": standard_deviation,
                        "Number of Outliers": num_outliers,
                        "Bias (%)": bias,
                        "Failure Rate (%)": percentage_outliers
                    }
                    summary_data_rounded = {k: round(v, 2) for k, v in summary_data.items()}

                    if not UseUL_LW:
                        summary_data2 = {
                            'Element': elem,
                            'Unit': None,  # will be set below
                            'CRM': certificate,
                            'Periode Range': f"{x_axis_min} - {x_axis_max}",
                            "Number of Samples": num_samples,
                            "Mean": mean_value_au,
                            "Expected Value": data_subset[expected_val_col].mean(),
                            "Standard Deviation": standard_deviation,
                            "Number of Outliers": num_outliers,
                            "Bias (%)": bias,
                            "Failure Rate (%)": percentage_outliers,
                        }
                        if isinstance(grp_values, tuple):
                            for field, val in zip(group_fields, grp_values):
                                summary_data2[field] = val
                        else:
                            summary_data2[group_fields[0]] = grp_values
                    else:
                        summary_data2 = {
                            'Element': elem,
                            'Unit': None,  # will be set below
                            'CRM': certificate,
                            'Periode Range': f"{x_axis_min} - {x_axis_max}",
                            "Number of Samples": num_samples,
                            "Mean": mean_value_au,
                            "Expected Value": data_subset[expected_val_col].mean(),
                            "Standard Deviation": standard_deviation,
                            "Number of Outliers": num_outliers,
                            "Bias (%)": bias,
                            "Failure Rate (%)": percentage_outliers,
                            'Source': data_subset[source_col].iloc[0]
                        }
                        if isinstance(grp_values, tuple):
                            for field, val in zip(group_fields, grp_values):
                                summary_data2[field] = val
                        else:
                            summary_data2[group_fields[0]] = grp_values

                    # --- Determine chart unit ---
                    if 'unit_col_name' in locals() and unit_col_name is not None:
                        unique_units = data_subset[unit_col_name].unique()
                        chart_unit   = unique_units[0] if len(unique_units) else ""
                    else:
                        chart_unit   = custom_unit if (unit_selection == "Custom") else unit
                    summary_data2['Unit'] = chart_unit

                    summary_data_rounded2 = {k: (round(v, 2) if isinstance(v, (int, float)) else v)
                                             for k, v in summary_data2.items()}
                    if group_fields:
                        ordered_keys = list(group_fields) + [k for k in summary_data_rounded2
                                                             if k not in group_fields]
                        summary_data_rounded2 = {k: summary_data_rounded2[k] for k in ordered_keys}

                    summary_data_rounded2['Bias (%)']        = round(summary_data_rounded2['Bias (%)'], 1)
                    summary_data_rounded2['Failure Rate (%)'] = round(summary_data_rounded2['Failure Rate (%)'], 1)

                    allstats.append(pd.DataFrame([summary_data_rounded2]))
                    st.dataframe(pd.DataFrame([summary_data_rounded2]))

                    # ------------------------------------------------------------------
                    #                              PLOTTING
                    # ------------------------------------------------------------------
                    if data_subset.empty:
                        st.warning(f"No data for group {group_label} – skipping.")
                        continue

                    if not (np.isfinite(y_axis_min) and np.isfinite(y_axis_max)):
                        y_axis_min = data_subset[grade_col].min()
                        y_axis_max = data_subset[grade_col].max()

                    fig, ax = plt.subplots(figsize=fig_size, dpi=150)
                    ax.scatter(data_subset['Sequence'],
                               data_subset[grade_col],
                               label=f'{elem}',
                               **common.marker_kwargs(sample_marker, Point_color, size=30))
                    mask_exceed_limits = ((data_subset[grade_col] > data_subset['Upper Bound (3SD)']) |
                                          (data_subset[grade_col] < data_subset['Lower Bound (3SD)']))
                    ax.plot(data_subset['Sequence'],
                            data_subset[expected_val_col],
                            label='Expected Value',
                            color=expected_color,
                            linestyle='--',
                            linewidth=1.5)
                    ax.scatter(data_subset['Sequence'][mask_exceed_limits],
                               data_subset[grade_col][mask_exceed_limits],
                               **common.marker_kwargs(failure_marker, failure_color, size=30, edge_color='#A36F67'),
                               label='Failures')
                    ax.axhline(y=mean_value_au,
                               color=mean_color,
                               linestyle='-',
                               label='Mean',
                               linewidth=1.75)
                    if not UseUL_LW:
                        ax.plot(data_subset['Sequence'],
                                data_subset['Upper Bound (2SD)'],
                                label='+2 SD',
                                color=twoSD_color,
                                linestyle='-',
                                linewidth=1.75)
                        ax.plot(data_subset['Sequence'],
                                data_subset['Lower Bound (2SD)'],
                                label='-2 SD',
                                color=twoSD_color,
                                linestyle='-',
                                linewidth=1.75)
                        ax.plot(data_subset['Sequence'],
                                data_subset['Upper Bound (3SD)'],
                                label='+3 SD',
                                color=threeSD_color,
                                linestyle='-',
                                linewidth=1.75)
                        ax.plot(data_subset['Sequence'],
                                data_subset['Lower Bound (3SD)'],
                                label='-3 SD',
                                color=threeSD_color,
                                linestyle='-',
                                linewidth=1.75)
                    else:
                        ax.plot(data_subset['Sequence'],
                                data_subset['Upper Bound (3SD)'],
                                label='Upper Limit',
                                color=threeSD_color,
                                linestyle='-',
                                linewidth=1.75)
                        ax.plot(data_subset['Sequence'],
                                data_subset['Lower Bound (3SD)'],
                                label='Lower Limit',
                                color=threeSD_color,
                                linestyle='-',
                                linewidth=1.75)

                    data_subset['Moving Mean'] = data_subset[grade_col].rolling(window=7).mean()
                    ax.plot(data_subset['Sequence'],
                            data_subset['Moving Mean'],
                            label='Moving Mean (7)',
                            color=movmean_color,
                            linestyle='--',
                            linewidth=0.75)

                    ax.set_xlabel('Date')
                    ax.set_ylabel(f'{elem} {chart_unit}', fontsize=15)
                    title_text = f'{certificate} - {elem} {chart_unit}'
                    if group_label:
                        title_text += f' - {group_label}'
                    if labname:
                        title_text += f' - {labname}'
                    ax.set_title(title_text, fontsize=20)
                    ax.grid(False)
                    ax.legend(loc='upper right',
                              bbox_to_anchor=(1, 1),
                              fancybox=True,
                              shadow=True)
                    ax.set_ylim(bottom=y_axis_min, top=y_axis_max)
                    ax.set_xticks(range(len(data_subset['Sequence'].cat.categories)))
                    ax.set_xticklabels(data_subset[date_col].dt.strftime('%Y-%m-%d'),
                                       rotation=x_text_rotation)
                    ax.margins(x=x_margin)
                    plt.xticks(rotation=x_text_rotation, ha='right')
                    tick_interval = max(1, len(data_subset) // nbin)
                    ax.xaxis.set_major_locator(MultipleLocator(tick_interval))

                    if show_summary:
                        summary_x_position = 0.99
                        summary_y_position = 0.02
                        summary_text = "\n".join([f"{k}: {v}" for k, v in summary_data_rounded.items()])
                        ax.text(summary_x_position,
                                summary_y_position,
                                summary_text,
                                transform=ax.transAxes,
                                verticalalignment='bottom',
                                horizontalalignment='right',
                                bbox=dict(facecolor='white',
                                          edgecolor='black',
                                          boxstyle='round,pad=0.5'))

                    ax.text(0.01, 0.02,
                            slr_text,
                            transform=ax.transAxes,
                            fontsize=8,
                            color='gray',
                            verticalalignment='bottom',
                            horizontalalignment='left')

                    plt.tight_layout()
                    fig_list.append(fig)
                    st.pyplot(fig)
            else:
                # ------------------------------------------------------------------
                #                  NO GROUPING FIELD SELECTED
                # ------------------------------------------------------------------
                data_subset = filtered_data.copy()
                group_label = ""
                group_key   = f"{unique_key_prefix}_all"

                x_axis_min = st.date_input("X axis min",
                                           key=f"x_min_{group_key}",
                                           value=data_subset[date_col].min())
                x_axis_max = st.date_input("X axis max",
                                           key=f"x_max_{group_key}",
                                           value=data_subset[date_col].max())
                y_axis_min = st.number_input('Y min',
                                             key=f"y_min_{group_key}",
                                             value=data_subset[grade_col].min() - data_subset[grade_col].std())
                y_axis_max = st.number_input('Y max',
                                             key=f"y_max_{group_key}",
                                             value=data_subset[grade_col].max() + data_subset[grade_col].std())
                labname = st.text_input('Lab Name', key=f"lab_{group_key}")

                if not UseUL_LW:
                    if not usemean:
                        expected_val = data_subset[expected_val_col].mean()
                        mean_value_au = data_subset[grade_col].mean()
                        if not sdcalc:
                            standard_deviation = data_subset[grade_col].std()
                            data_subset['Upper Bound (2SD)'] = expected_val + (twostd * standard_deviation)
                            data_subset['Lower Bound (2SD)'] = expected_val - (twostd * standard_deviation)
                            data_subset['Upper Bound (3SD)'] = expected_val + (threestd * standard_deviation)
                            data_subset['Lower Bound (3SD)'] = expected_val - (threestd * standard_deviation)
                        else:
                            if len(data_subset[std_col].unique()) == 1:
                                standard_deviation = data_subset[std_col].unique()[0]
                                data_subset['Upper Bound (2SD)'] = expected_val + (twostd * standard_deviation)
                                data_subset['Lower Bound (2SD)'] = expected_val - (twostd * standard_deviation)
                                data_subset['Upper Bound (3SD)'] = expected_val + (threestd * standard_deviation)
                                data_subset['Lower Bound (3SD)'] = expected_val - (threestd * standard_deviation)
                            else:
                                st.warning('There are multiple values in the STD column; please check the file for any errors')
                    else:
                        expected_val = data_subset[expected_val_col].mean()
                        mean_value_au = data_subset[grade_col].mean()
                        if not sdcalc:
                            standard_deviation = data_subset[grade_col].std()
                            data_subset['Upper Bound (2SD)'] = mean_value_au + (twostd * standard_deviation)
                            data_subset['Lower Bound (2SD)'] = mean_value_au - (twostd * standard_deviation)
                            data_subset['Upper Bound (3SD)'] = mean_value_au + (threestd * standard_deviation)
                            data_subset['Lower Bound (3SD)'] = mean_value_au - (threestd * standard_deviation)
                        else:
                            if len(data_subset[std_col].unique()) == 1:
                                standard_deviation = data_subset[std_col].unique()[0]
                                data_subset['Upper Bound (2SD)'] = mean_value_au + (twostd * standard_deviation)
                                data_subset['Lower Bound (2SD)'] = mean_value_au - (twostd * standard_deviation)
                                data_subset['Upper Bound (3SD)'] = mean_value_au + (threestd * standard_deviation)
                                data_subset['Lower Bound (3SD)'] = mean_value_au - (threestd * standard_deviation)
                            else:
                                st.warning('There are multiple values in the STD column; please check the file for any errors')
                else:
                    expected_val = data_subset[expected_val_col].mean()
                    mean_value_au = data_subset[grade_col].mean()
                    standard_deviation = data_subset[grade_col].std()
                    data_subset['Upper Bound (3SD)'] = data_subset[upperlimit_col].mean()
                    data_subset['Lower Bound (3SD)'] = data_subset[lowerlimit_col].mean()

                data_subset = data_subset.sort_values(by=[date_col]).reset_index(drop=True)

                x_axis_min_dt = pd.to_datetime(x_axis_min)
                x_axis_max_dt = pd.to_datetime(x_axis_max) + pd.Timedelta(days=1)
                if x_axis_max_dt > x_axis_min_dt:
                    data_subset = data_subset[(data_subset[date_col] >= x_axis_min_dt) &
                                              (data_subset[date_col] <= x_axis_max_dt)]
                elif x_axis_max_dt == x_axis_min_dt:
                    data_subset = data_subset[data_subset[date_col].dt.date == x_axis_min]
                else:
                    st.write('There is a problem with dates')
                data_subset = common.filter_dates(data_subset, date_col, crm_date_opts).reset_index(drop=True)
                if data_subset.empty:
                    st.warning(f"No data in the dates shown for {certificate} – skipping.")
                    continue

                data_subset['Sequence'] = range(0, len(data_subset))
                st.dataframe(data_subset)

                nbin = st.slider('Number of Ticks', 1, max(1, len(data_subset)-1), 3,
                                 key=f"nbin_{group_key}")
                data_subset['Sequence'] = data_subset['Sequence'].astype('category')

                num_samples  = len(data_subset[grade_col])
                num_outliers = sum((data_subset[grade_col] > data_subset['Upper Bound (3SD)']) |
                                   (data_subset[grade_col] < data_subset['Lower Bound (3SD)']))
                bias = ((mean_value_au / data_subset[expected_val_col].iloc[0]) - 1) * 100
                percentage_outliers = (num_outliers / num_samples) * 100

                summary_data = {
                    "Number of Samples": num_samples,
                    "Mean": mean_value_au,
                    "Expected Value": data_subset[expected_val_col].mean(),
                    "Standard Deviation": standard_deviation,
                    "Number of Outliers": num_outliers,
                    "Bias (%)": bias,
                    "Failure Rate (%)": percentage_outliers
                }
                summary_data_rounded = {k: round(v, 2) for k, v in summary_data.items()}

                if not UseUL_LW:
                    summary_data2 = {
                        'Element': elem,
                        'Unit': None,  # will be set below
                        'CRM': certificate,
                        'Periode Range': f"{x_axis_min} - {x_axis_max}",
                        "Number of Samples": num_samples,
                        "Mean": mean_value_au,
                        "Expected Value": data_subset[expected_val_col].mean(),
                        "Standard Deviation": standard_deviation,
                        "Number of Outliers": num_outliers,
                        "Bias (%)": bias,
                        "Failure Rate (%)": percentage_outliers,
                    }
                else:
                    summary_data2 = {
                        'Element': elem,
                        'Unit': None,  # will be set below
                        'CRM': certificate,
                        'Periode Range': f"{x_axis_min} - {x_axis_max}",
                        "Number of Samples": num_samples,
                        "Mean": mean_value_au,
                        "Expected Value": data_subset[expected_val_col].mean(),
                        "Standard Deviation": standard_deviation,
                        "Number of Outliers": num_outliers,
                        "Bias (%)": bias,
                        "Failure Rate (%)": percentage_outliers,
                        'Source': data_subset[source_col].iloc[0]
                    }

                # --- Determine chart unit ---
                if 'unit_col_name' in locals() and unit_col_name is not None:
                    unique_units = data_subset[unit_col_name].unique()
                    chart_unit   = unique_units[0] if len(unique_units) else ""
                else:
                    chart_unit   = custom_unit if (unit_selection == "Custom") else unit
                summary_data2['Unit'] = chart_unit

                summary_data_rounded2 = {k: (round(v, 2) if isinstance(v, (int, float)) else v)
                                         for k, v in summary_data2.items()}

                summary_data_rounded2['Bias (%)']        = round(summary_data_rounded2['Bias (%)'], 1)
                summary_data_rounded2['Failure Rate (%)'] = round(summary_data_rounded2['Failure Rate (%)'], 1)

                allstats.append(pd.DataFrame([summary_data_rounded2]))
                st.dataframe(pd.DataFrame([summary_data_rounded2]))

                # ------------------------------------------------------------------
                #                              PLOTTING
                # ------------------------------------------------------------------
                if data_subset.empty:
                    st.warning(f"No data for {certificate} – skipping.")
                    continue

                if not (np.isfinite(y_axis_min) and np.isfinite(y_axis_max)):
                    y_axis_min = data_subset[grade_col].min()
                    y_axis_max = data_subset[grade_col].max()

                fig, ax = plt.subplots(figsize=fig_size, dpi=150)
                ax.scatter(data_subset['Sequence'],
                           data_subset[grade_col],
                           label=f'{elem}',
                           **common.marker_kwargs(sample_marker, Point_color, size=30))
                mask_exceed_limits = ((data_subset[grade_col] > data_subset['Upper Bound (3SD)']) |
                                      (data_subset[grade_col] < data_subset['Lower Bound (3SD)']))
                ax.plot(data_subset['Sequence'],
                        data_subset[expected_val_col],
                        label='Expected Value',
                        color=expected_color,
                        linestyle='--',
                        linewidth=1.5)
                ax.scatter(data_subset['Sequence'][mask_exceed_limits],
                           data_subset[grade_col][mask_exceed_limits],
                           **common.marker_kwargs(failure_marker, failure_color, size=30, edge_color='#A36F67'),
                           label='Failures')
                ax.axhline(y=mean_value_au,
                           color=mean_color,
                           linestyle='-',
                           label='Mean',
                           linewidth=1.75)
                if not UseUL_LW:
                    ax.plot(data_subset['Sequence'],
                            data_subset['Upper Bound (2SD)'],
                            label='+2 SD',
                            color=twoSD_color,
                            linestyle='-',
                            linewidth=1.75)
                    ax.plot(data_subset['Sequence'],
                            data_subset['Lower Bound (2SD)'],
                            label='-2 SD',
                            color=twoSD_color,
                            linestyle='-',
                            linewidth=1.75)
                    ax.plot(data_subset['Sequence'],
                            data_subset['Upper Bound (3SD)'],
                            label='+3 SD',
                            color=threeSD_color,
                            linestyle='-',
                            linewidth=1.75)
                    ax.plot(data_subset['Sequence'],
                            data_subset['Lower Bound (3SD)'],
                            label='-3 SD',
                            color=threeSD_color,
                            linestyle='-',
                            linewidth=1.75)
                else:
                    ax.plot(data_subset['Sequence'],
                            data_subset['Upper Bound (3SD)'],
                            label='Upper Limit',
                            color=threeSD_color,
                            linestyle='-',
                            linewidth=1.75)
                    ax.plot(data_subset['Sequence'],
                            data_subset['Lower Bound (3SD)'],
                            label='Lower Limit',
                            color=threeSD_color,
                            linestyle='-',
                            linewidth=1.75)

                data_subset['Moving Mean'] = data_subset[grade_col].rolling(window=7).mean()
                ax.plot(data_subset['Sequence'],
                        data_subset['Moving Mean'],
                        label='Moving Mean (7)',
                        color=movmean_color,
                        linestyle='--',
                        linewidth=0.75)

                ax.set_xlabel('Date')
                ax.set_ylabel(f'{elem} {chart_unit}', fontsize=15)
                title_text = f'{certificate} - {elem} {chart_unit}'
                if labname:
                    title_text += f' - {labname}'
                ax.set_title(title_text, fontsize=20)
                ax.grid(False)
                ax.legend(loc='upper right',
                          bbox_to_anchor=(1, 1),
                          fancybox=True,
                          shadow=True)
                ax.set_ylim(bottom=y_axis_min, top=y_axis_max)
                ax.set_xticks(range(len(data_subset['Sequence'].cat.categories)))
                ax.set_xticklabels(data_subset[date_col].dt.strftime('%Y-%m-%d'),
                                   rotation=x_text_rotation)
                ax.margins(x=x_margin)
                plt.xticks(rotation=x_text_rotation, ha='right')
                tick_interval = max(1, len(data_subset) // nbin)
                ax.xaxis.set_major_locator(MultipleLocator(tick_interval))

                if show_summary:
                    summary_x_position = 0.99
                    summary_y_position = 0.02
                    summary_text = "\n".join([f"{k}: {v}" for k, v in summary_data_rounded.items()])
                    ax.text(summary_x_position,
                            summary_y_position,
                            summary_text,
                            transform=ax.transAxes,
                            verticalalignment='bottom',
                            horizontalalignment='right',
                            bbox=dict(facecolor='white',
                                      edgecolor='black',
                                      boxstyle='round,pad=0.5'))

                ax.text(0.01, 0.02,
                        slr_text,
                        transform=ax.transAxes,
                        fontsize=8,
                        color='gray',
                        verticalalignment='bottom',
                        horizontalalignment='left')

                plt.tight_layout()
                fig_list.append(fig)
                st.pyplot(fig)

        # ------------------------------------------------------------------
        #         END OF MAIN ELEMENT LOOP
        # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    #        COMBINED SUMMARY TABLE + PRESENTATION GENERATION
    # ------------------------------------------------------------------
    try:
        combined_stats = pd.concat(allstats, ignore_index=True)
        st.dataframe(combined_stats)

        csv = combined_stats.to_csv(index=False).encode('utf-8')
        st.download_button("Download Combined Summary Table",
                           data=csv,
                           file_name="combined_summary.csv",
                           mime="text/csv")
    except Exception:
        pass

    if st.button('Generate Presentation'):
        st.session_state['crm_ppt_bytes'] = build_presentation_bytes(fig_list)
    if st.session_state.get('crm_ppt_bytes'):
        st.download_button(
            "Download plots.pptx",
            data=st.session_state['crm_ppt_bytes'],
            file_name="standards_plots.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

# ------------------------------------------------------------------
#                     SAVE SESSION STATE
# ------------------------------------------------------------------
try:
    session_state_json = json.dumps(serialize_session_state(st.session_state))
except (TypeError, ValueError):
    # serialize_session_state already drops non-serialisable values, so this
    # should not happen — but never let a serialisation hiccup remove the
    # Save Progress button. Fall back to an empty snapshot.
    session_state_json = "{}"
st.download_button('Save Progress',
                   data=session_state_json,
                   file_name='saved_progress.json',
                   mime='application/json')
