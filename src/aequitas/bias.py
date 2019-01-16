import logging
from sys import exit

from aequitas.preprocessing import get_attr_cols
from aequitas.plotting import Plot
assemble_ref_groups = Plot._assemble_ref_groups

import pandas as pd
from scipy import stats

logging.getLogger(__name__)

__author__ = "Rayid Ghani, Pedro Saleiro <saleiro@uchicago.edu>, Loren Hinkson"
__copyright__ = "Copyright \xa9 2018. The University of Chicago. All Rights Reserved."

class Bias(object):
    """
    """
    default_key_columns = ('model_id', 'score_threshold', 'attribute_name')
    all_group_metrics = ('ppr', 'pprev', 'precision', 'fdr', 'for', 'fpr',
                         'fnr', 'tpr', 'tnr', 'npv')
    non_attr_cols = ('score', 'model_id', 'as_of_date', 'entity_id', 'rank_abs',
                     'rank_pct', 'id', 'label_value')
    significance_measures = ('fpr', 'fnr')

    def __init__(self, key_columns=default_key_columns, sample_df=None,
                 non_attr_cols=non_attr_cols,
                 significance_cols=significance_measures,
                 input_group_metrics=all_group_metrics, fill_divbyzero=None):
        """

        :param key_columns:
        :param input_group_metrics:
        :param fill_divbyzero:
        """
        self.key_columns = list(key_columns)
        self.input_group_metrics = list(input_group_metrics)

        if not fill_divbyzero:
            self.fill_divbyzero = 10.00000
        else:
            self.fill_divbyzero = fill_divbyzero
        self.non_attr_cols = non_attr_cols
        self.significance_cols = significance_cols
        # if sample_df:
        #     self.samples = self.get_measure_sample(sample_df, attribute, measure)

    def get_disparity_min_metric(self, df, original_df, key_columns=None,
                                 input_group_metrics=None, fill_divbyzero=None,
                                 check_significance=None,  alpha = 5e-2,
                                 mask_significance = True):
        """
        Calculates several ratios using the group metrics value and dividing by
        the minimum group metric value among all groups defined by each attribute

        :param df: the resulting dataframe from the group get_crosstabs
        :param input_group_metrics: the columns list corresponding to the group
        metrics for which we want to calculate the disparity values
        :return: a dataframe
        """

        print('get_disparity_min_metric()')
        if not key_columns:
            key_columns = self.key_columns
        if not input_group_metrics:
            input_group_metrics = self.input_group_metrics
        if not fill_divbyzero:
            fill_divbyzero = self.fill_divbyzero
        if not check_significance:
            check_significance = self.significance_cols

        print('get_disparity_min_metric')
        fill_zeros = {}
        for group_metric in input_group_metrics:
            fill_zeros[group_metric + '_disparity'] = 1.000000
            try:
                # this groupby is being called every cycle. maybe we can create a list of df_groups
                # and merge df at the end? it can not be simply put outside the loop(the merge...)
                df_min_idx = df.loc[df.groupby(key_columns)[group_metric].idxmin()]
                # but we also want to get the group_value of the reference group for each bias metric
                df_to_merge = pd.DataFrame()
                df_to_merge[key_columns + [group_metric + '_disparity', group_metric +
                                           '_ref_group_value']] = \
                    df_min_idx[key_columns + [group_metric, 'attribute_value']]
            except KeyError:
                logging.error(
                    'get_bias_min_metric:: one of the following columns is not in the input '
                    'dataframe : model_id ,parameter,attribute_name or any of the input_group_metrics '
                    'list')
                exit(1)
            df = df.merge(df_to_merge, on=key_columns)
            # creating disparity by dividing each group metric value by the corresponding min
            # value from the groups of the target attribute
            df[group_metric + '_disparity'] = df[group_metric] / df[group_metric + '_disparity']
        # We are capping the disparity values to 10.0 when divided by zero...
        df = df.replace(pd.np.inf, fill_divbyzero)
        # df = df.fillna(value=fill_zeros)

        # add statisticall_significance

        check_significance = [measure for measure in check_significance if measure in df.columns]
        ref_groups_dict = assemble_ref_groups(df, ref_group_flag='_ref_group_value',
                                       specific_measures=check_significance,
                                       label_score_ref='fpr')

        attr_cols = df['attribute_name'].unique()

        # for attribute in attr_cols:
        #
        #     if 'fpr' in check_significance:
        #         label_score_ref = ref_groups_dict[attribute]['fpr']
        #     else:
        #         label_score_ref = ref_groups_dict[attribute]['fnr']
        #
        #     if 'label_value' in original_df.columns:
        #         ref_groups_dict[attribute]['label_value'] = label_score_ref
        #
        #     ref_groups_dict[attribute]['score'] = label_score_ref

        # run significance method on bias-augmented crosstab based on false
        # positives, false negatives, scores, and label values in original df
        self.get_statistical_significance(
            original_df, df, ref_dict=ref_groups_dict, score_thresholds=None,
            model_id=1, attr_cols=attr_cols, aplha=5e-2,
            mask_significance=mask_significance)

        # if specified, apply T/F mask to significance columns
        if mask_significance:
            significance_cols = df.columns[df.columns.str.contains('_significance')]
            truemask = df.loc[:, significance_cols] < alpha
            falsemask = df.loc[:, significance_cols] >= alpha

            df.loc[:, significance_cols] = pd.np.select(
                [truemask, falsemask], [True, False], default=None)

        return df



    def get_disparity_major_group(self, df, original_df, key_columns=None,
                                  input_group_metrics=None,
                                  fill_divbyzero=None, check_significance=None,
                                  alpha = 5e-2, mask_significance = True):
        """
            Calculates the bias (disparity) metrics for the predefined list of group metrics
            using the majority group within each attribute as the reference group (denominator)

        :param df: the returning dataframe from the group.get_crosstabs
        :return: a dataframe with the bias metrics as new columns and the ref group,
                it must have the same number of rows as the input dataframe
        """
        print('get_disparity_major_group()')
        if not key_columns:
            key_columns = self.key_columns
        if not input_group_metrics:
            input_group_metrics = self.input_group_metrics
        if not fill_divbyzero:
            fill_divbyzero = self.fill_divbyzero
        if not check_significance:
            check_significance = self.significance_cols

        try:
            df_major_group = df.loc[df.groupby(key_columns)['group_size'].idxmax()]
        except KeyError:
            logging.error('get_bias_major_group:: one of the following columns is not on the input '
                          'dataframe : model_id ,parameter,attribute_name, group_size ')
            exit(1)
        disparity_metrics = [col + '_disparity' for col in input_group_metrics]
        df_to_merge = pd.DataFrame()
        # we created the df_to_merge has a subset of the df_ref_group containing the target ref
        # group values which are now labeled as _disparity but we still need to perform the division
        df_to_merge[key_columns + disparity_metrics] = df_major_group[
            key_columns + input_group_metrics]
        # we now need to create the ref_group_value columns in the df_to_merge
        for col in input_group_metrics:
            df_to_merge[col + '_ref_group_value'] = df_major_group['attribute_value']
        df = df.merge(df_to_merge, on=key_columns)
        df[disparity_metrics] = df[input_group_metrics].divide(df[disparity_metrics].values)
        # We are capping the disparity values to 10.0 when divided by zero...
        df = df.replace(pd.np.inf, fill_divbyzero)
        # when there is a zero in the numerator and a zero in denominator it is considered NaN
        # after division, so if 0/0 we assume 1.0 disparity (they are the same...)
        fill_zeros = {metric: 1.000000 for metric in disparity_metrics}
        # df = df.fillna(value=fill_zeros)

        # default is to use the same ref groups as df, need to add functionality to
        # complie ref_groups_dict based on a passed ref group for a given measure
        check_significance = [measure for measure in check_significance if measure in df.columns]
        ref_groups_dict = assemble_ref_groups(df, ref_group_flag='_ref_group_value',
                                       specific_measures=['fpr', 'fnr'])

        attr_cols = df['attribute_name'].unique()
        for attribute in attr_cols:
            largest_group = df_major_group.loc[df_major_group['attribute_name'] == attribute,
                                               'attribute_value'].values.tolist()[0]
            ref_groups_dict[attribute]['label_value'] = largest_group
            ref_groups_dict[attribute]['score'] = largest_group

        # run significance method on bias-augmented crosstab based on false
        # positives, false negatives, scores, and label values in original df
        self.get_statistical_significance(
            original_df, df, ref_dict=ref_groups_dict, score_thresholds=None,
            model_id=1, attr_cols=attr_cols, aplha=5e-2,
            mask_significance=mask_significance)

        # if specified, apply T/F mask to significance columns
        if mask_significance:
            significance_cols = df.columns[df.columns.str.contains('_significance')]
            truemask = df.loc[:, significance_cols] < alpha
            falsemask = df.loc[:, significance_cols] >= alpha

            df.loc[:, significance_cols] = pd.np.select(
                [truemask, falsemask], [True, False], default=None)

        return df

    def verify_ref_groups_dict_len(self, df, ref_groups_dict):
        if len(ref_groups_dict) != len(df['attribute_name'].unique()):
            raise ValueError

    def verify_ref_group_loc(self, group_slice):
        if len(group_slice) < 1:
            raise ValueError

    def get_disparity_predefined_groups(self, df, original_df, ref_groups_dict,
                                        key_columns=None,
                                        input_group_metrics=None,
                                        fill_divbyzero=None,
                                        check_significance=None, alpha=5e-2,
                                        mask_significance=True):
        """
            Calculates the bias (disparity) metrics for the predefined list of input group metrics
            using a predefined reference group value for each attribute which is passed using
            ref_groups_dict ({'attr1':'val1', 'attr2':'val2'})

        :param df: the output dataframe of the group.get_crosstabs
        :param ref_groups_dict: a dictionary {attribute_name:attribute_value, ...}
        :param key_columns: optional, the key columns to use on joins
        :param input_group_metrics: optional, the group metrics to be used for creating the new
        disparity metrics
        :param fill_divbyzero: optional, fill value to use when divided by zero
        :return: a dataframe with same number of rows as the input but with additional
        disparity metrics columns and ref_group_values
        """
        print('get_disparity_predefined_group()')
        if not key_columns:
            key_columns = self.key_columns
        if not input_group_metrics:
            input_group_metrics = self.input_group_metrics
        if not fill_divbyzero:
            fill_divbyzero = self.fill_divbyzero
        if not check_significance:
            check_significance = self.significance_cols
        try:
            self.verify_ref_groups_dict_len(df, ref_groups_dict)
        except ValueError:
            logging.error('Bias.get_disparity_predefined_groups(): the number of predefined group '
                          'values to use as reference is less than the actual number of '
                          'attributes in the input dataframe.')
            exit(1)
        df_ref_group = pd.DataFrame()
        try:
            for key, val in ref_groups_dict.items():
                group_slice = df.loc[(df['attribute_name'] == key) & (df['attribute_value'] == val)]
                self.verify_ref_group_loc(group_slice)
                df_ref_group = pd.concat([df_ref_group, group_slice])
        except (KeyError, ValueError):
            logging.error('get_disparity_predefined_groups(): reference groups and values provided '
                          'do not exist as columns/values in the input dataframe.(Note: check for syntax errors)')
            exit(1)
        disparity_metrics = [col + '_disparity' for col in input_group_metrics]
        df_to_merge = pd.DataFrame()
        # we created the df_to_merge has a subset of the df_ref_group containing the target ref
        # group values which are now labeled as _disparity but we still need to perform the division
        df_to_merge[key_columns + disparity_metrics] = df_ref_group[
            key_columns + input_group_metrics]
        # we now need to create the ref_group_value columns in the df_to_merge
        for col in input_group_metrics:
            df_to_merge[col + '_ref_group_value'] = df_ref_group['attribute_value']
        df = df.merge(df_to_merge, on=key_columns)
        df[disparity_metrics] = df[input_group_metrics].divide(df[disparity_metrics].values)
        # We are capping the disparity values to 10.0 when divided by zero...
        df = df.replace(pd.np.inf, fill_divbyzero)
        # when there is a zero in the numerator and a zero in denominator it is considered NaN
        # after division, so if 0/0 we assume 1.0 disparity (they are the same...)
        fill_zeros = {metric: 1.000000 for metric in disparity_metrics}
        # df = df.fillna(value=fill_zeros)

        # for predefined groups, use the largest of the predefined groups as
        # ref group for score and label value
        check_significance = \
            [measure for measure in check_significance if measure in df.columns]

        # complile dictionary of reference groups based on bias-augmented crosstab
        full_ref_dict = {}
        for key, val in ref_groups_dict.items():
            full_ref_dict[key] = {'label_value': val,
                                  'score': val}
            for measure in check_significance:
                full_ref_dict[key][measure] = val

        # run significance method on bias-augmented crosstab based on false
        # positives, false negatives, scores, and label values in original df
        self.get_statistical_significance(
            original_df, df, ref_dict=full_ref_dict, score_thresholds=None,
            model_id=1, attr_cols=None, aplha=5e-2,
            mask_significance=mask_significance)

        # if specified, apply T/F mask to significance columns
        if mask_significance:
            significance_cols = df.columns[df.columns.str.contains('_significance')]
            truemask = df.loc[:, significance_cols] < alpha
            falsemask = df.loc[:, significance_cols] >= alpha

            df.loc[:, significance_cols] = pd.np.select(
                [truemask, falsemask], [True, False], default=None)

        return df


    @classmethod
    def get_measure_sample(cls, df, attribute, measure):
        return df.groupby(attribute).apply(lambda f: f[measure].values.tolist()).to_dict()

    # @classmethod
    # def retrieve_all_samples(cls, df):
    #     for

    @classmethod
    def check_equal_variance(cls, sample_dict, ref_group, alpha=5e-2):
        eq_variance = {ref_group: True}
        for attr_value, sample in sample_dict.items():
            _, normality_p = stats.normaltest(sample, axis=None, nan_policy='omit')

            if normality_p < alpha:
                if attr_value == ref_group:
                    # if ref_group is not normal, can't use f-test or bartlett,
                    # so skip ahead to check for equal varience with ref_group
                    # using levene test for all groups
                    for group, sample_list in sample_dict.items():
                        _, equal_variance_p = stats.levene(sample_dict[ref_group],
                                                           sample_list,
                                                           center='median')
                        if equal_variance_p < alpha:
                            eq_variance[group] = False
                        else:
                            eq_variance[group] = True
                    return eq_variance

                # if a non-ref group is not normal, can't use f-test or bartlett,
                # check for equal variance with ref_group using levene test
                _, equal_variance_p = stats.levene(sample_dict[ref_group], sample, center='median')
                if equal_variance_p < alpha:
                    eq_variance[attr_value] = False
                else:
                    eq_variance[attr_value] = True
                if attr_value == ref_group:
                    ref_group_normality = False

        # case when some non-ref groups pass normality test, use bartlett test
        # between each sample list and ref group to check for equal variance
        untested_groups = sample_dict.keys() - eq_variance.keys() - set(ref_group)
        untested = {key: val for (key, val) in sample_dict.items() if key in untested_groups}

        for sample, sample_list in untested.items():
            _, equal_variance_p = stats.bartlett(sample_dict[ref_group], sample_list)
            if equal_variance_p < alpha:
                eq_variance[attr_value] = False
            else:
                eq_variance[attr_value] = True
        return eq_variance

    @classmethod
    def check_alpha(cls, x, alpha=5e-2):
        print(f"{x}: {type(x)}")
        if x >= alpha:
            return False
        else:
            return True


    @classmethod
    def calculate_significance(cls, original_df, disparity_df, attribute, measure, ref_dict,
                               alpha=5e-2, mask_significance=True):
        binaries_lookup = {'label_value': 'label_value', 'binary_fp': 'fpr',
                           'binary_fn': 'fnr', 'binary_score': 'score'}

        ref_group = ref_dict[attribute][binaries_lookup.get(measure)]

        # create dictionary of "samples" (binary values for false positive,
        # false negative, label value, score) based on original data frame
        sample_dict = cls.get_measure_sample(df=original_df, attribute=attribute,
                                             measure=measure)
        # run SciPy equal variance tests between each group and a given
        # reference group, store results in dictionary to pass to statistical
        # significance tests
        eq_variance_dict = cls.check_equal_variance(sample_dict=sample_dict,
                                                    ref_group=ref_group,
                                                    alpha=alpha)

        # run SciPy statistical significance test between each group and
        # reference group
        for attr_val, eq_var in sample_dict.items():
            _, difference_significance_p = stats.ttest_ind(
                sample_dict[ref_group], sample_dict[attr_val], axis=None,
                equal_var=eq_variance_dict[attr_val], nan_policy='omit')

            measure = "".join(measure.split('binary_'))

            # add column to crosstab to indicate statistical significance
            disparity_df.loc[disparity_df['attribute_value'] == attr_val, measure + '_significance'] = \
                difference_significance_p


        return disparity_df



    @classmethod
    def get_statistical_significance(cls, original_df, disparity_df, ref_dict,
                                     score_thresholds=None, model_id=1,
                                     attr_cols=None, aplha=5e-2,
                                     mask_significance=True):
        if 'label_value' not in original_df.columns:
            raise ValueError(
                "Column 'label_value' not in dataframe. Label values are "
                "required for computing statistical significance of supervised "
                "metrics.")

        if attr_cols is None:
            non_attr_cols = [
                'id', 'model_id', 'entity_id', 'score', 'label_value',
                'rank_abs', 'rank_pct']
            # index of the columns that are attributes
            attr_cols = original_df.columns[~original_df.columns.isin(non_attr_cols)]

        for col in attr_cols:
            # find the priors_df
            col_group = original_df.fillna({col: 'pd.np.nan'}).groupby(col)
            counts = col_group.size()

        # check if all attr_cols exist in df
        check = [col in original_df.columns for col in attr_cols]
        if False in check:
            raise ValueError(
                f"Not all attribute columns provided '{attr_cols}' exist in "
                f"input dataframe!")

        # check if all columns are strings:
        non_string_cols = \
            original_df.columns[(original_df.dtypes != object) & (original_df.dtypes != str) & (
                original_df.columns.isin(attr_cols))]

        if non_string_cols.empty is False:
            logging.error(
                'get_statistical_significance: statistical significance was '
                'not calculated. There are non-string cols within attr_cols.')
            exit(1)

        # if no score_thresholds are provided, we assume that rank_abs equals
        # the number  of 1s in the score column; it also serves as flag to set
        # parameter to 'binary'

        count_ones = None
        if not score_thresholds:
            original_df['score'] = original_df['score'].astype(float)
            count_ones = original_df['score'].value_counts().get(1.0, 0)
            score_thresholds = {'rank_abs': [count_ones]}

        original_df = original_df.sort_values('score', ascending=False)
        original_df['rank_abs'] = range(1, len(original_df) + 1)
        original_df['rank_pct'] = original_df['rank_abs'] / len(original_df)

        binary_false_pos = lambda rank_col, label_col, thres: lambda x: (
                (x[rank_col] <= thres) & (x[label_col] == 0)).astype(int)

        binary_false_neg = lambda rank_col, label_col, thres: lambda x: (
                (x[rank_col] > thres) & (x[label_col] == 1)).astype(int)

        binary_score = lambda rank_col, label_col, thres: lambda x: (
                x[rank_col] <= thres).astype(int)

        binary_col_functions = {'binary_score': binary_score,
                                'binary_fp': binary_false_pos,
                                'binary_fn': binary_false_neg,
                                }

        for attribute in attr_cols:
            # fill missing values with NaN
            col_group = original_df.fillna({attribute: 'pd.np.nan'}).groupby(attribute)

            for thres_unit, thres_values in score_thresholds.items():
                for thres_val in thres_values:
                    # flag = 0
                    # k = (original_df[thres_unit] <= thres_val).sum()
                    # score_threshold = \
                    #     'binary 0/1' if count_ones != None else \
                    #         str(thres_val) + '_' + thres_unit[-3:]

                    for name, func in binary_col_functions.items():
                        func = func(thres_unit, 'label_value', thres_val)
                        original_df[name] = col_group.apply(func).reset_index(level=0,
                                                                     drop=True)
            measures = list(binary_col_functions.keys())
            measures += ['label_value']
            measures.sort()

            for measure in measures:
                cls.calculate_significance(
                    original_df, disparity_df, attribute, measure,
                    ref_dict=ref_dict,
                    alpha=aplha, mask_significance=mask_significance)
        return disparity_df

    def list_disparities(self, df):
        '''
        View all calculated disparities in table
        :return: list of disparity metrics
        '''
        return list(df.columns[df.columns.str.contains('_disparity')])

    def list_significance(self, df):
        '''
        View all calculated disparities in table
        :return: list of disparity metrics
        '''
        return list(df.columns[df.columns.str.contains('_significance')])

    def list_absolute_metrics(self, df):
        '''
        View all calculated disparities in table
        :return: list of absolute group metrics
        '''
        return list(set(self.input_group_metrics) & set(df.columns))
