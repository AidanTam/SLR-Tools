# Import necessary libraries
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
import streamlit as st
import matplotlib.pyplot as plt
from scipy.stats import variation




st.set_page_config(layout="wide")

# File upload and user inputs
# The tool compares any two paired datasets (not only blast holes vs drill
# holes), so the labels below follow the names typed into Data Type 1 / 2.
# Labels that include those names get fixed keys: Streamlit keys a widget by
# its label otherwise, and renaming a dataset would reset every selection.
BHS_file = st.sidebar.file_uploader("Dataset 1")
BHS_type = st.sidebar.text_input("Data Type 1", 'Dataset 1' )
BHS_color = st.sidebar.color_picker("Pick A Color for "+BHS_type, "#667545", key="color_1")
DDH_file = st.sidebar.file_uploader("Dataset 2")
DDH_type = st.sidebar.text_input("Data Type 2", 'Dataset 2' )
DDH_color = st.sidebar.color_picker("Pick A Color for "+DDH_type, "#D6F591", key="color_2")
GradecapBHS = st.sidebar.number_input("Capping Value for "+BHS_type, value=999999.00, key="cap_1")
GradecapDDH = st.sidebar.number_input("Capping Value for "+DDH_type, value=999999.00, key="cap_2")
table1,table2= st.tabs(['tab1','tab2'])
if BHS_file and DDH_file:
    with table1:
        tab1, tab2 = st.columns(2)

        BHS = pd.read_csv(BHS_file)
        DDH = pd.read_csv(DDH_file)
        BHS = BHS.add_prefix(BHS_type+'_')
        DDH = DDH.add_prefix(DDH_type+'_')


        BHS.dropna(how='all', inplace=True)
        DDH.dropna(how='all', inplace=True)

        # Reset the index after dropping blank rows. dropna leaves a
        # non-contiguous index, and the nearest-neighbour join below concats
        # the reset-indexed `nearest_points` onto `result_df` with axis=1 —
        # pandas aligns those on the index, so a gapped BHS index misaligns
        # every match after the first gap and injects NaN rows (the whole
        # "one to many" result breaks). The "one to one" path masked this by
        # dropping the NaN rows during de-duplication.
        BHS.reset_index(drop=True, inplace=True)
        DDH.reset_index(drop=True, inplace=True)

        # st.data_editor(BHS)
        BHS_Grade_Field = st.sidebar.selectbox("Select the "+BHS_type+" Grade Field ", BHS.columns, key="grade_1")
        DDH_Grade_Field = st.sidebar.selectbox("Select the "+DDH_type+" Grade Field ", DDH.columns, key="grade_2")
        BHS_len_Field = st.sidebar.selectbox("Select the "+BHS_type+" Length Field ", BHS.columns, key="len_1")
        DDH_len_Field = st.sidebar.selectbox("Select the "+DDH_type+" Length Field ", DDH.columns, key="len_2")

        DDH_coordinate_fields = st.sidebar.multiselect("Select the "+DDH_type+" coordinates fields", DDH.columns, key="coords_2")
        BHS_coordinate_fields = st.sidebar.multiselect("Select the "+BHS_type+" coordinates fields", BHS.columns, key="coords_1")
        DDH_from_to = st.sidebar.multiselect("Select the "+DDH_type+" ID, From, To Fields", DDH.columns, key="from_to_2")

        if DDH_Grade_Field:
            element = st.sidebar.text_input("element", DDH_Grade_Field )
            unit = st.sidebar.text_input("Unit", ' ' )

        # The nearest-neighbour search below needs both coordinate field sets.
        # Bail out with guidance until they're chosen, otherwise `tree`/`indices`
        # are never defined and the tool throws a NameError right after upload.
        if not (DDH_coordinate_fields and BHS_coordinate_fields):
            st.info("Select the "+BHS_type+" and "+DDH_type+" coordinate fields in the sidebar to run the comparison.")
            st.stop()

        if len(DDH_coordinate_fields) != len(BHS_coordinate_fields):
            st.warning("Pick the same number of coordinate fields for "+BHS_type+" and "+DDH_type+".")
            st.stop()

        tree = cKDTree(DDH[DDH_coordinate_fields])
        distances, indices = tree.query(BHS[BHS_coordinate_fields])

        nearest_points = DDH.iloc[indices].reset_index(drop=True)
        result_df = BHS.copy()
        result_df['distance'] = distances
        result_df = pd.concat([result_df, nearest_points], axis=1)
        one_to_one = st.sidebar.checkbox("One to One")

        if one_to_one:
            # De-duplication needs the Drill ID/From/To fields to identify a
            # unique drill-hole interval. Without them drop_duplicates(subset=[])
            # treats every row as identical and collapses the result to a single
            # row, so guard against an empty selection instead of silently
            # returning one row.
            if not DDH_from_to:
                st.warning("Select the "+DDH_type+" ID, From, To fields in the sidebar to use One to One matching.")
                st.stop()
            result_df = result_df.sort_values(by='distance').drop_duplicates(subset=DDH_from_to, keep='first')
        # result_df.to_csv(r'C:\Application\Get_Nearest\output\Dorota.csv')
        st.data_editor(result_df,key='test')

        capped_result_df = result_df.copy()
        uncapped_result_df = result_df.copy()

        # Use the clip to Cap
        # capped_result_df[BHS_Grade_Field] = pd.to_numeric(capped_result_df[BHS_Grade_Field], errors='coerce')
        # capped_result_df = capped_result_df[capped_result_df[BHS_Grade_Field].notna()]
        non_numeric = capped_result_df[~capped_result_df[BHS_Grade_Field].apply(lambda x: isinstance(x, (int, float)))]
        st.write(non_numeric)
        capped_result_df[BHS_Grade_Field] = capped_result_df[BHS_Grade_Field].clip(upper=GradecapBHS)


        # capped_result_df[DDH_Grade_Field] = pd.to_numeric(capped_result_df[DDH_Grade_Field], errors='coerce')
        # capped_result_df = capped_result_df[capped_result_df[DDH_Grade_Field].notna()]


        capped_result_df[DDH_Grade_Field] = capped_result_df[DDH_Grade_Field].clip(upper=GradecapDDH)

        col1, col2, col3 = st.sidebar.columns(3)
        mindist = col1.number_input("Min Distance", value=10.0)
        maxdist = col2.number_input("Max Distance", value=20.0)
        stepdist = col3.number_input("Step", value=2.0)
        gradetext = st.sidebar.text_input("Cutoff Grades Seperated by comma", '0,0.5,0.75,1')
        cleangrades = gradetext.replace(' ', '').split(',')
        gradelist = [float(num) for num in cleangrades]

        def process_data(result_df, BHS_Grade_Field, DDH_Grade_Field, BHS_len_Field, DDH_len_Field):
            tabledata = []
            for Distance_threshhold in np.arange(mindist, maxdist + stepdist, stepdist):
                for Cutoff_Grade in gradelist:
                    # st.dataframe(result_df)

                    Filtered_data_bh = result_df[(result_df['distance'] <= Distance_threshhold) & (result_df[BHS_Grade_Field] >= Cutoff_Grade)]
                    Filtered_data_dh = result_df[(result_df['distance'] <= Distance_threshhold) & (result_df[DDH_Grade_Field] >= Cutoff_Grade)]
                    bh_len_sum = Filtered_data_bh[BHS_len_Field].sum()
                    dh_len_sum = Filtered_data_dh[DDH_len_Field].sum()
                    bh_au_weighted_sum = (Filtered_data_bh[BHS_len_Field] * Filtered_data_bh[BHS_Grade_Field]).sum()
                    dh_au_weighted_sum = (Filtered_data_dh[DDH_len_Field] * Filtered_data_dh[DDH_Grade_Field]).sum()
                    dh_Au_G_t = dh_au_weighted_sum / dh_len_sum
                    bh_Au_G_t = bh_au_weighted_sum / bh_len_sum

                    data = {' ': [BHS_type, DDH_type],
                            'Meters': [bh_len_sum, dh_len_sum],
                            element+' '+ unit: [bh_Au_G_t, dh_Au_G_t],
                            element+' '+ unit+'*meters': [bh_au_weighted_sum, dh_au_weighted_sum],
                            'Distance': [Distance_threshhold, Distance_threshhold],
                            'Cutoff': [Cutoff_Grade, Cutoff_Grade],
                            'Data count':[len(Filtered_data_bh),len(Filtered_data_dh)]}
                    Final_Results = pd.DataFrame(data=data)
                    tabledata.append(Final_Results)
            return pd.concat(tabledata, ignore_index=True)
        



        def process_data_nocutoff(result_df, BHS_Grade_Field, DDH_Grade_Field, BHS_len_Field, DDH_len_Field):
            tabledata = []
            for Distance_threshhold in np.arange(mindist, maxdist + stepdist, stepdist):
                    Filtered_data_bh = result_df[(result_df['distance'] <= Distance_threshhold)]
                    Filtered_data_dh = result_df[(result_df['distance'] <= Distance_threshhold) ]
                    bh_len_sum = Filtered_data_bh[BHS_len_Field].sum()
                    dh_len_sum = Filtered_data_dh[DDH_len_Field].sum()
                    bh_au_weighted_sum = (Filtered_data_bh[BHS_len_Field] * Filtered_data_bh[BHS_Grade_Field]).sum()
                    dh_au_weighted_sum = (Filtered_data_dh[DDH_len_Field] * Filtered_data_dh[DDH_Grade_Field]).sum()
                    dh_Au_G_t = dh_au_weighted_sum / dh_len_sum
                    bh_Au_G_t = bh_au_weighted_sum / bh_len_sum

                    data = {' ': [BHS_type, DDH_type],
                            'Meters': [bh_len_sum, dh_len_sum],
                            element+' '+ unit: [bh_Au_G_t, dh_Au_G_t],
                            element+' '+ unit+'*meters': [bh_au_weighted_sum, dh_au_weighted_sum],
                            'Distance': [Distance_threshhold, Distance_threshhold],
                            'Data count':[len(Filtered_data_bh),len(Filtered_data_dh)]}
                    Final_Results = pd.DataFrame(data=data)
                    tabledata.append(Final_Results)
            return pd.concat(tabledata, ignore_index=True)

        merged_table_capped = process_data(capped_result_df, BHS_Grade_Field, DDH_Grade_Field, BHS_len_Field, DDH_len_Field)
        merged_table_uncapped = process_data(uncapped_result_df, BHS_Grade_Field, DDH_Grade_Field, BHS_len_Field, DDH_len_Field)
        histogramdf = capped_result_df[capped_result_df['distance'] <= mindist]

        
        
        bin_size = st.slider("Select Bin Size", min_value=1, max_value=150, value=10)
        # num_xticks = st.slider("Select Number of X-Ticks", min_value=2, max_value=50, value=10)

        # df =result_df[result_df['distance'] <= mindist]
            # Determine the common range for bins
        min_grade = min(histogramdf[BHS_Grade_Field].min(), histogramdf[DDH_Grade_Field].min())
        max_grade = max(histogramdf[BHS_Grade_Field].max(), histogramdf[DDH_Grade_Field].max())
        
        #### Fixing 0 min value
        
        safe_min_grade = min_grade if min_grade > 0 else 0.01  # or any small positive number
        bins = np.logspace(np.log10(safe_min_grade), np.log10(max_grade), bin_size + 1)

        # Calculate the common bin edges
        # bins = np.logspace(np.log10(min_grade), np.log10(max_grade), bin_size + 1)
        #### Fixing 0 min value end

        
        # Plot stacked histograms
        plt.figure(figsize=(10, 6))

        # Histogram for BHS_Grade_Field
        plt.hist(histogramdf[BHS_Grade_Field].dropna(), bins=bins, alpha=0.5,color=BHS_color, label=BHS_type, edgecolor='black')

        # Histogram for DDH_Grade_Field
        plt.hist(histogramdf[DDH_Grade_Field].dropna(), bins=bins, alpha=0.5,color=DDH_color, label=DDH_type, edgecolor='black')

        plt.xlabel(element+' '+ unit)
        plt.ylabel('Data Count')
        plt.title('Grade Distribution Comparisons '+ 'based on a distance of '+str(mindist)+' m')
        plt.legend(loc='upper right')
        plt.xscale('log')
        # Set x-ticks based on the slider for the number of x-ticks
    # Set fixed x-ticks





        # #check if min grade is 0
        # if min_grade <= 0 or np.isnan(min_grade) or np.isnan(max_grade):
        #     fixed_xticks = []
        # else:
        #     fixed_xticks = [10**i for i in range(int(np.floor(np.log10(min_grade))), int(np.ceil(np.log10(max_grade))) + 1)]
        if min_grade <= 0 or np.isnan(min_grade) or np.isnan(max_grade):
            tick_start = 0  # or pick a safe default like -1
        else:
            tick_start = int(np.floor(np.log10(min_grade)))

        tick_end = int(np.ceil(np.log10(max_grade)))
        fixed_xticks = [10**i for i in range(tick_start, tick_end + 1)]




        # fixed_xticks = [10**i for i in range(int(np.floor(np.log10(min_grade))), int(np.ceil(np.log10(max_grade))) + 1)]
        plt.xticks(fixed_xticks, [f'{tick:.1f}' if tick < 1 else f'{int(tick)}' for tick in fixed_xticks], rotation=90)  # Adjust rotation for better readability if needed
        
        st.pyplot(plt)

        
        tab1.title('Capped Results')
        tab1.dataframe(merged_table_capped)
        tab2.title('Uncapped Results')
        tab2.dataframe(merged_table_uncapped)


        merged_table_capped2 = process_data_nocutoff(capped_result_df, BHS_Grade_Field, DDH_Grade_Field, BHS_len_Field, DDH_len_Field)
        merged_table_uncapped2 = process_data_nocutoff(uncapped_result_df, BHS_Grade_Field, DDH_Grade_Field, BHS_len_Field, DDH_len_Field)
        # merged_table_capped2.to_csv('C:\Application\Get_Nearest\output\merged_table_capped2.csv')
        # merged_table_uncapped2.to_csv('C:\Application\Get_Nearest\output\merged_table_uncapped2.csv')
        #####Distance Graph #####
            ###Filter the dataframes
        ddh_capped = merged_table_capped2[merged_table_capped2[' '] == DDH_type]
        bhs_capped = merged_table_capped2[merged_table_capped2[' '] == BHS_type]

        ddh_uncapped = merged_table_uncapped2[merged_table_uncapped2[' '] == DDH_type]
        bhs_uncapped = merged_table_uncapped2[merged_table_uncapped2[' '] == BHS_type]

        # Plot the curves for capped dataframe
        # fig1, ax1 = plt.subplots(figsize=(10, 6))

        # ax1.plot(ddh_capped['Distance'], ddh_capped[element+' '+ unit], label=DDH_type+' Capped Au g/t', color='blue')
        # ax1.plot(bhs_capped['Distance'], bhs_capped[element+' '+ unit], label=BHS_type+' Capped Au g/t', color='red')
        # ax1.set_xlabel('Distance')
        # ax1.set_ylabel(element+' '+ unit)
        # ax1.set_title('Capped Data:'+ element+' '+ unit+' and Meters vs. Distance')
        # ax1.legend(loc='upper left')

        # ax2 = ax1.twinx()
        # ax2.plot(ddh_capped['Distance'], ddh_capped['Meters'], label=DDH_type+' Capped Meters', color='cyan', linestyle='dashed')
        # ax2.plot(bhs_capped['Distance'], bhs_capped['Meters'], label=BHS_type+' Capped Meters', color='magenta', linestyle='dashed')
        # ax2.set_ylabel('Meters')
        # ax2.legend(loc='upper right')

        # Plot the curves for uncapped dataframe
        # fig2, ax3 = plt.subplots(figsize=(10, 6))

        # ax3.plot(ddh_uncapped['Distance'], ddh_uncapped['Au g/t'], label='DDH Uncapped Au g/t', color='green')
        # ax3.plot(bhs_uncapped['Distance'], bhs_uncapped['Au g/t'], label='BHS Uncapped Au g/t', color='orange')
        # ax3.set_xlabel('Distance')
        # ax3.set_ylabel('Au g/t')
        # ax3.set_title('Uncapped Data: Au g/t and Meters vs. Distance')
        # ax3.legend(loc='upper left')

        # ax4 = ax3.twinx()
        # ax4.plot(ddh_uncapped['Distance'], ddh_uncapped['Meters'], label='DDH Uncapped Meters', color='cyan', linestyle='dashed')
        # ax4.plot(bhs_uncapped['Distance'], bhs_uncapped['Meters'], label='BHS Uncapped Meters', color='magenta', linestyle='dashed')
        # ax4.set_ylabel('Meters')
        # ax4.legend(loc='upper right')

        # # Use Streamlit to display the plots
        # st.pyplot(fig1)
        # st.pyplot(fig2)

        # tab1.dataframe(ddh_capped)
        # tab2.dataframe(bhs_capped)
        # ddh_capped.to_csv('C:\Application\Get_Nearest\output\ddh.csv')
        # bhs_capped.to_csv('C:\Application\Get_Nearest\output\gbhs.csv')
        
        # Combine the two datasets
        combined_df_capped = pd.concat([ddh_capped, bhs_capped])
        # st.dataframe(combined_df_capped)
        # Plotting with overlapping bars starting from 0
        fig3, ax3 = plt.subplots(figsize=(14, 7))

        # Define the width for overlapping bars and ensure bars touch each other
        width = st.slider("Bar Width", min_value=0.1, max_value=stepdist, value=stepdist)
        # st.title(DDH_type)
        # st.data_editor(ddh_capped) 
        # st.title(BHS_type)
        # st.data_editor(bhs_capped)       # Plot BHS
        ax3.bar(bhs_capped['Distance'], bhs_capped[element+' '+ unit], width=width, label=BHS_type, color=BHS_color, edgecolor='black', alpha=0.7)
        # Plot DDH
        ax3.bar(ddh_capped['Distance'], ddh_capped[element+' '+ unit], width=width, label=DDH_type, color=DDH_color, edgecolor='black', alpha=0.7)

        # Add labels and title
        ax3.set_xlabel('Separation Distance (mts)')
        ax3.set_ylabel(element+' '+ unit)
        # ax3.set_title('(xxx deposit) gold distribution comparison: Blasthole and Drillhole vs. Distance - all data')
        ax3.set_xticks(combined_df_capped['Distance'])
        ax3.set_xticklabels(combined_df_capped['Distance'].astype(int))

        # Create a second y-axis to plot the meters curve
        ax4 = ax3.twinx()
        ax4.plot(ddh_capped['Distance'], ddh_capped['Data count'], color='#1E1E1E', marker='o', linestyle='--', linewidth=2, markersize=5, label='Data count')
        # ax4.plot(bhs_capped['Distance'], bhs_capped['Meters'], color='green', marker='o', linestyle='--', linewidth=2, markersize=5, label='Meters')
        ax4.set_ylabel('Data Count')
        ax4.set_ylim(0, combined_df_capped['Data count'].max() * 1.2)

        # Add legends
        fig3.legend(loc='upper right', bbox_to_anchor=(0.9, 0.9))
        # st.data_editor(result_df[result_df['distance'] <= mindist])
        # result_df[result_df['distance'] <= mindist].to_csv(r'C:\Application\Get_Nearest\output\results.csv')
        # Display the plot
        st.pyplot(fig3)







        # Calculate basic statistics on the filtered DataFrame
        stats_data = result_df[result_df['distance'] <= mindist].describe()
        # st.dataframe(result_df[result_df['distance'] <= mindist])
        # Select only numeric columns for the coefficient of variation calculation
        numeric_cols = result_df[result_df['distance'] <= mindist].select_dtypes(include=[np.number])

        # Calculate the coefficient of variation
        coef_var = numeric_cols.apply(lambda x: variation(x.dropna()), axis=0)

        # Convert to DataFrame and transpose to match the format of stats_data
        coef_var_df = pd.DataFrame(coef_var, columns=['coef_var']).T

        # Append coefficient of variation to the stats_data DataFrame
        stats_data = pd.concat([stats_data, coef_var_df])

        # Display in Streamlit
        st.header('Descriptive Statistics based on a distance of  '+str(mindist))
        st.dataframe(stats_data[[BHS_Grade_Field,DDH_Grade_Field]])







        def convert_to_ranges(lst):
            return [[lst[i], lst[i+1]] for i in range(len(lst)-1)]
        alldf = []
        newgradelist = gradelist
        newgradelist.append(max(histogramdf[BHS_Grade_Field].max(),histogramdf[DDH_Grade_Field].max()))
        graderanges = convert_to_ranges(newgradelist)
        for i in graderanges :
            with st.expander('Grade range '+ str(i[0]) + ' - ' + str(i[1])):
                Filter_data_bh = histogramdf[(histogramdf[BHS_Grade_Field] >= i[0]) & (histogramdf[BHS_Grade_Field] < i[1])]
                Filter_data_dh = histogramdf[(histogramdf[DDH_Grade_Field] >= i[0]) & (histogramdf[DDH_Grade_Field] < i[1])]
                bh_len_sum = Filter_data_bh[BHS_len_Field].sum()
                dh_len_sum = Filter_data_dh[DDH_len_Field].sum()
                bh_au_weighted_sum = (Filter_data_bh[BHS_len_Field] * Filter_data_bh[BHS_Grade_Field]).sum()
                dh_au_weighted_sum = (Filter_data_dh[DDH_len_Field] * Filter_data_dh[DDH_Grade_Field]).sum()
                dh_Au_G_t = dh_au_weighted_sum / dh_len_sum
                bh_Au_G_t = bh_au_weighted_sum / bh_len_sum
                data = {'Dataset': [BHS_type,DDH_type, 'Ratio'],
                                    'Meters': [bh_len_sum, dh_len_sum, (dh_len_sum/bh_len_sum)*100 ],
                                    element+' '+ unit: [bh_Au_G_t, dh_Au_G_t,(dh_Au_G_t/bh_Au_G_t)*100],
                                    element+' '+ unit+'*meters': [bh_au_weighted_sum, dh_au_weighted_sum,(dh_au_weighted_sum/bh_au_weighted_sum)*100],
                                    'Cutoff': [str(i[0]) + ' - ' + str(i[1]), str(i[0]) + ' - ' + str(i[1]),str(i[0]) + ' - ' + str(i[1])]}
                Finaldf = pd.DataFrame(data=data)
                alldf.append(Finaldf)
                st.dataframe(Finaldf)
        histdf = pd.concat(alldf, ignore_index=True)

        st.download_button(
            label="Download Compiled Table",
            data=histdf.to_csv().encode("utf-8"),
            file_name="Compiled Table.csv",
            mime="text/csv",
        )

        col4,col5 = st.columns(2)
        ddh_df = histdf[histdf['Dataset']==DDH_type]
        bhs_df = histdf[histdf['Dataset']==BHS_type] 
        col4.dataframe(ddh_df)
        col5.dataframe(bhs_df)
        # cutoff_ranges = sorted(set(ddh_df['Cutoff']).union(set(bhs_df['Cutoff'])))
        cutoff_ranges = sorted(set(ddh_df['Cutoff']).union(set(bhs_df['Cutoff'])), key=lambda x: float(x.split(' - ')[0]))
        def plot_histograms(ddh_df, bhs_df):
            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            # Use the same bins for both histograms
            bins = range(len(cutoff_ranges) + 1)

            # Meters Histogram
            ddh_meters = ddh_df['Meters'].groupby(ddh_df['Cutoff']).sum().reindex(cutoff_ranges).fillna(0)
            bhs_meters = bhs_df['Meters'].groupby(bhs_df['Cutoff']).sum().reindex(cutoff_ranges).fillna(0)
            axes[0].bar(bins[:-1], ddh_meters, color=DDH_color,width=0.4, label=DDH_type, align='center')
            axes[0].bar(bins[:-1], bhs_meters,color=BHS_color, width=0.4, label=BHS_type, align='edge')
            axes[0].set_title('Meters')
            axes[0].set_xlabel('Cut Off Ranges')
            axes[0].set_ylabel('Meters')
            axes[0].set_xticks(bins[:-1])
            axes[0].set_xticklabels(cutoff_ranges, rotation=45, ha="right")
            axes[0].legend()

            # Grade Histogram
            ddh_grade = ddh_df[element+' '+ unit].groupby(ddh_df['Cutoff']).sum().reindex(cutoff_ranges).fillna(0)
            bhs_grade = bhs_df[element+' '+ unit].groupby(bhs_df['Cutoff']).sum().reindex(cutoff_ranges).fillna(0)
            axes[1].bar(bins[:-1], ddh_grade,color=DDH_color, width=0.4, label=DDH_type, align='center')
            axes[1].bar(bins[:-1], bhs_grade,color=BHS_color ,width=0.4, label=BHS_type, align='edge')
            axes[1].set_title(element+' '+ unit)
            axes[1].set_xlabel('Cut Off Ranges')
            axes[1].set_ylabel(element+' '+ unit)
            axes[1].set_xticks(bins[:-1])
            axes[1].set_xticklabels(cutoff_ranges, rotation=45, ha="right")
            axes[1].legend()

            # g/t*meters Histogram
            ddh_gt_meters = ddh_df[element+' '+ unit+'*meters'].groupby(ddh_df['Cutoff']).sum().reindex(cutoff_ranges).fillna(0)
            bhs_gt_meters = bhs_df[element+' '+ unit+'*meters'].groupby(bhs_df['Cutoff']).sum().reindex(cutoff_ranges).fillna(0)
            axes[2].bar(bins[:-1], ddh_gt_meters,color=DDH_color, width=0.4, label=DDH_type, align='center')
            axes[2].bar(bins[:-1], bhs_gt_meters,color=BHS_color, width=0.4, label=BHS_type, align='edge')
            axes[2].set_title(element+' '+ unit+'*meters')
            axes[2].set_xlabel('Cut Off Ranges')
            axes[2].set_ylabel(element+' '+ unit+'*meters')
            axes[2].set_xticks(bins[:-1])
            axes[2].set_xticklabels(cutoff_ranges, rotation=45, ha="right")
            axes[2].legend()

            plt.tight_layout()
            return fig


        # st.title('Geological Data Analysis')
        st.header('The histograms are based on a distance of '+str(mindist)+' m')
        st.pyplot(plot_histograms(ddh_df,bhs_df))


    with table2:
        # The pygwalker explorer is an optional extra. Import it lazily so an
        # incompatible/missing pygwalker (e.g. its Streamlit integration lagging
        # a newer Streamlit release) degrades this one tab instead of crashing
        # the whole tool at import time.
        try:
            from pygwalker.api.streamlit import StreamlitRenderer
            pyg_app = StreamlitRenderer(result_df)
            pyg_app.explorer()
        except Exception:
            pass

