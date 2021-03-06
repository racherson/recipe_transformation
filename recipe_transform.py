import collections
import functools
import json
import nltk
import urllib.request
from bs4 import BeautifulSoup
# from pprint import pprint


try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
try:
    nltk.data.find('wordnet')
except LookupError:
    nltk.download('wordnet')


# global variables for stopwords, custom methods/tools/units arrays

STOPWORDS = nltk.corpus.stopwords.words('english')
PUNCTUATION = [',', '.', '!', '?', '(', ')']
STOPWORDS.extend(PUNCTUATION)
METHODS = ['blend', 'cut', 'strain', 'roast', 'slice', 'flip', 'baste', 'simmer', 'grate', 'drain', 'saute', 'broil', 'boil', 'poach', 'bake', 'grill', 'fry', 'bake', 'heat', 'mix', 'chop', 'grate', 'stir', 'shake', 'mince', 'crush', 'squeeze', 'dice', 'rub', 'cook']
TOOLS = ['pan', 'grater', 'whisk', 'pot', 'spatula', 'tong', 'oven', 'knife']
UNITS = ['tablespoon', 'teaspoon', 'cup', 'clove', 'pound']


# categorized ingredients dictionary (found at https://github.com/olivergoodman/food-recipes/blob/master/transforms.py)

INGREDIENT_CATEGORIES = {
    'healthy_fats': ['olive oil', 'sunflower oil', 'soybean oil', 'corn oil',  'sesame oil',  'peanut oil'],
    'unhealthy_fats': ['butter', 'lard', 'shortening', 'canola oil', 'margarine',  'coconut oil',  'tallow',  'cream',
                       'milk fat',  'palm oil',  'palm kemel oil',  'chicken fat',  'hydrogenated oils'],
    'healthy_protein': ['peas',  'beans', 'eggs', 'crab', 'fish', 'chicken', 'tofu', 'liver', 'turkey'],
    'unhealthy_protein': ['ground beef', 'beef', 'pork', 'lamb'],
    'meat': ['scallop', 'sausage', 'bacon', 'beef', 'pork', 'lamb', 'crab', 'fish', 'chicken', 'turkey', 'liver',
             'duck', 'tuna', 'lobster', 'salmon', 'shrimp', 'crayfish', 'crawfish', 'ribs', 'pheasant', 'escargot',
             'snail', 'bass', 'sturgeon', 'trout', 'flounder', 'carp', 'quail', 'goose'],
    'healthy_dairy': ['fat free milk', 'low fat milk', 'yogurt',  'low fat cheese'],
    'unhealthy_dairy': ['reduced-fat milk', 'cream cheese', 'whole milk', 'butter', 'cheese', 'whipped cream',
                        'sour cream'],
    'healthy_salts': ['low sodium soy sauce', 'sea salt', 'kosher salt'],
    'unhealthy_salts': ['soy sauce', 'table salt', 'salt'],
    'healthy_grains': ['oat cereal', 'wild rice', 'oatmeal', 'whole rye', 'buckwheat', 'rolled oats', 'quinoa',
                       'bulgur', 'millet', 'brown rice', 'whole wheat pasta'],
    'unhealthy_grains': ['macaroni', 'noodles', 'spaghetti', 'white rice', 'white bread', 'regular white pasta'],
    'healthy_sugars': ['real fruit jam', 'fruit juice concentrates', 'monk fruit extract', 'cane sugar', 'molasses',
                       'brown rice syrup' 'stevia', 'honey', 'maple syrup', 'agave syrup', 'coconut sugar',
                       'date sugar', 'sugar alcohols', 'brown sugar'],
    'unhealthy_sugars': ['aspartame', 'acesulfame K', 'sucralose', 'white sugar', 'corn syrup', 'chocolate syrup'],
    'spice': ['ajwain', 'allspice', 'almond meal', 'anise seed', 'annatto seed', 'arrowroot powder', 'cacao', 'cumin',
              'bell pepper', 'beetroot powder', 'chia seeds', 'cloves', 'chiles', 'cinnamon', 'cloves', 'coriander',
              'dill seed', 'garlic', 'ginger', 'mustard', 'onion', 'paprika', 'cayenne', 'pepper', 'red pepper',
              'black pepper', 'shallots', 'star anise', 'turmeric', 'vanilla extract'],
    'herb': ['basil', 'bay leaves', 'celery flakes', 'chervil', 'cilantro', 'curry', 'dill weed', 'dried chives',
             'epatoze', 'file powder', 'kaffire lime', 'lavender', 'lemongrass', 'mint', 'oregano', 'parsley',
             'rosemary', 'sage', 'tarragon', 'thyme']
}


# custom synonym dictionary

SYNONYMS = {
    'stock': 'broth',
    'cayenne': 'cayenne pepper',
}


# recipe class definition

class Recipe:
    def __init__(self, soup):
        self.soup = soup
        # get recipe name
        name = self.soup.find('h1', id='recipe-main-content')
        self.name = name.string
        # get recipe ingredients
        ingredients = self.soup.find_all('span', class_='recipe-ingred_txt added')
        self.ingredients = [add_ingredient(ingredient.contents[0]) for ingredient in ingredients]
        # get recipe steps
        self.steps = self.get_steps()
        # get recipe tools
        self.tools, methods_counter = self.get_tools_methods()
        # get primary method and any other methods
        self.primary_method = methods_counter.most_common(1)[0][0]
        del methods_counter[self.primary_method]
        self.other_methods = list(methods_counter)
        # check to see if recipe is for baking or not
        if self.primary_method == 'bake' or 'bake' in self.other_methods:
            self.bake = True
        else:
            self.bake = False
        # initialize ingredient and method switches dictionaries
        self.ingredient_switches = {}
        self.method_switches = {}
        # print recipe
        self.print_recipe()

    def get_steps(self):
        global SYNONYMS
        # get steps from soup
        steps_elements = self.soup.find('ol', class_='list-numbers recipe-directions__list')('li')
        steps = []
        # format steps to be numbered
        for count, step_element in enumerate(steps_elements):
            step_text = str(count+1) + '. ' + step_element.find('span').string.strip()
            # account for ingredient synonyms
            for synonym in SYNONYMS:
                step_text = step_text.replace(synonym, SYNONYMS[synonym])
            steps.append(Step(step_text, self.ingredients))
        return steps

    def get_tools_methods(self):
        # get tools and methods from a recipe
        global STOPWORDS
        global METHODS
        global TOOLS
        tools = set()  # unique set
        methods_counter = collections.Counter()  # frequency mapping
        for step in self.steps:
            # tokenize each step
            tokens = nltk.word_tokenize(step.text)
            tokens = [token.lower() for token in tokens if token not in STOPWORDS]
            bigrams = nltk.bigrams(tokens)
            step_methods = set()
            # check unigrams for tools and methods
            for token in tokens:
                if token in TOOLS:
                    tools.add(token)
                if token in METHODS:
                    methods_counter.update([token])
                    step_methods.add(token)
            # check bigrams for tools and methods
            for token in bigrams:
                if token in TOOLS:
                    tools.add(token)
                if token in METHODS:
                    methods_counter.update([token])
                    step_methods.add(token)
            step.methods = list(step_methods)
        return list(tools), methods_counter

    def alter_steps(self):
        # alter the step text with the ingredient and method substitutions made
        word_ends = [' ', '.', ',']
        for step in self.steps:
            # replace ingredients
            for switch in self.ingredient_switches:
                for word_end in word_ends:
                    step.text = step.text.replace(switch + word_end, self.ingredient_switches[switch] + word_end)
            # replace methods
            for switch in self.method_switches:
                for word_end in word_ends:
                    step.text = step.text.replace(switch + word_end, self.method_switches[switch] + word_end)
            tokens = nltk.word_tokenize(step.text)
            tokens = [token.lower() for token in tokens if token not in STOPWORDS]
            tokens = [token for i, token in enumerate(tokens) if i != 0 and token == tokens[i-1]]
            for token in tokens:
                step.text = step.text.replace(token + ' ' + token, token)

    def make_healthy(self):
        # change recipe from unhealthy to healthy
        print('\nMaking healthy...')
        # baking substitutions
        if self.bake:
            # substitution dictionaries
            global healthy_baking_substitutions_names
            global healthy_baking_substitutions_adjectives
            global healthy_baking_substitutions_categories
            global healthy_baking_substitutions_exceptions
            global healthy_baking_substitutions_methods
            for step in self.steps:
                # look through each ingredient substitution dictionary and make the changes
                make_substitutions_with(step.ingredients,
                                        self.ingredient_switches,
                                        healthy_baking_substitutions_names,
                                        healthy_baking_substitutions_adjectives,
                                        healthy_baking_substitutions_categories,
                                        healthy_baking_substitutions_exceptions,
                                        False)
                # look through the method substitution dictionary
                for method in step.methods:
                    if method in healthy_baking_substitutions_methods:
                        # find substitutions to be made
                        self.method_switches[method] = healthy_baking_substitutions_methods[method]
                # make the substitution in the step's method list
                step.methods = [self.method_switches[x] if x in self.method_switches else x for x in step.methods]
        else:  # non-baking substitutions
            # substitution dictionaries
            global healthy_substitutions_names
            global healthy_substitutions_adjectives
            global healthy_substitutions_categories
            global healthy_substitutions_exceptions
            global healthy_substitutions_methods
            # look through each ingredient substitution dictionary and make the changes
            for step in self.steps:
                make_substitutions_with(step.ingredients,
                                        self.ingredient_switches,
                                        healthy_substitutions_names,
                                        healthy_substitutions_adjectives,
                                        healthy_substitutions_categories,
                                        healthy_substitutions_exceptions,
                                        False)
                # look through the method substitution dictionary
                for method in step.methods:
                    if method in healthy_substitutions_methods:
                        # find substitutions to be made
                        self.method_switches[method] = healthy_substitutions_methods[method]
                # make the substitution in the step's method list
                step.methods = [self.method_switches[x] if x in self.method_switches else x for x in step.methods]
        self.alter_steps()
        print('\nAltered Steps:')
        for step in self.steps:
            print(step)

    def make_unhealthy(self):
        # change recipe from healthy to unhealthy
        print('\nMaking unhealthy...')
        # Baking substitutions
        if self.bake:
            # substitution dictionaries
            global unhealthy_baking_substitutions_names
            global unhealthy_baking_substitutions_adjectives
            global unhealthy_baking_substitutions_categories
            global unhealthy_baking_substitutions_exceptions
            global unhealthy_baking_substitutions_methods
            for step in self.steps:
                make_substitutions_with(step.ingredients,
                                        self.ingredient_switches,
                                        unhealthy_baking_substitutions_names,
                                        unhealthy_baking_substitutions_adjectives,
                                        unhealthy_baking_substitutions_categories,
                                        unhealthy_baking_substitutions_exceptions,
                                        False)
                for method in step.methods:
                    # find method substitutions to be made
                    if method in unhealthy_baking_substitutions_methods:
                        self.method_switches[method] = unhealthy_baking_substitutions_methods[method]
                # make the substitution in the method list
                step.methods = [self.method_switches[x] if x in self.method_switches else x for x in step.methods]
        else:  # non-baking substitution dictionaries
            global unhealthy_substitutions_names
            global unhealthy_substitutions_adjectives
            global unhealthy_substitutions_categories
            global unhealthy_substitutions_exceptions
            global unhealthy_substitutions_methods
            for step in self.steps:
                # substitute ingredients
                make_substitutions_with(step.ingredients,
                                        self.ingredient_switches,
                                        unhealthy_substitutions_names,
                                        unhealthy_substitutions_adjectives,
                                        unhealthy_substitutions_categories,
                                        unhealthy_substitutions_exceptions,
                                        False)
                # substitute methods
                for method in step.methods:
                    if method in unhealthy_substitutions_methods:
                        self.method_switches[method] = unhealthy_substitutions_methods[method]
                step.methods = [self.method_switches[x] if x in self.method_switches else x for x in step.methods]
        self.alter_steps()
        next_count = int(self.steps[-1].text[0]) + 1
        if not self.bake:
            # if non-baking recipe, add extra salt step/ingredient
            salt = Ingredient('salt', None, 'seasoning', None, None)
            self.ingredients.append(salt)
            step_text = str(next_count) + '. Sprinkle a lot of extra salt over the whole meal.'
            new_step = Step(step_text, [salt])
            new_step.methods = ['sprinkle']
            self.steps.append(new_step)
        else:
            # if baking recipe, add extra frosting step/ingredient
            frosting = Ingredient('frosting', 'chocolate', 'topping', 2, 'cups')
            self.ingredients.append(frosting)
            step_text = str(next_count) + '. Spread frosting over everything.'
            new_step = Step(step_text, [frosting])
            new_step.methods = ['spread']
            self.steps.append(new_step)
        print('\nAltered Ingredients:')
        for ingredient in self.ingredients:
            print(ingredient)
        print('\nAltered Steps:')
        for step in self.steps:
            print(step)

    def make_vegetarian(self):
        # change recipe from non vegetarian to vegetarian
        # vegetarian substitution dictionaries
        global vegetarian_substitutions_names
        global vegetarian_substitutions_adjectives
        global vegetarian_substitutions_categories
        global vegetarian_substitutions_exceptions
        print('\nMaking vegetarian...')
        for step in self.steps:
            # make all ingredient substitutions
            make_substitutions_with(step.ingredients,
                                    self.ingredient_switches,
                                    vegetarian_substitutions_names,
                                    vegetarian_substitutions_adjectives,
                                    vegetarian_substitutions_categories,
                                    vegetarian_substitutions_exceptions,
                                    True)
        self.alter_steps()
        print('\nAltered Steps:')
        for step in self.steps:
            print(step)

    def make_non_vegetarian(self):
        # change recipe from vegetarian to non vegetarian
        # meatify substitution dictionaries
        global non_vegetarian_substitutions_names
        global non_vegetarian_substitutions_adjectives
        global non_vegetarian_substitutions_categories
        global non_vegetarian_substitutions_exceptions
        print('\nMaking non-vegetarian...')
        for step in self.steps:
            # make all ingredient substitutions
            make_substitutions_with(step.ingredients,
                                    self.ingredient_switches,
                                    non_vegetarian_substitutions_names,
                                    non_vegetarian_substitutions_adjectives,
                                    non_vegetarian_substitutions_categories,
                                    non_vegetarian_substitutions_exceptions,
                                    False)
        self.alter_steps()
        print('\nAltered Steps:')
        for step in self.steps:
            print(step)

    def make_thai(self):
        # change recipe to thai style of cuisine
        # thai substitution dictionaries
        global thai_substitutions_names
        global thai_substitutions_adjectives
        global thai_substitutions_categories
        global thai_substitutions_exceptions
        print('\nMaking Thai...')
        for step in self.steps:
            # make all ingredient substitutions
            make_substitutions_with(step.ingredients,
                                    self.ingredient_switches,
                                    thai_substitutions_names,
                                    thai_substitutions_adjectives,
                                    thai_substitutions_categories,
                                    thai_substitutions_exceptions,
                                    False)
        self.alter_steps()
        print('\nAltered Steps:')
        for step in self.steps:
            print(step)

    def make_mediterranean(self):
        # change recipe to mediterranean style of cuisine
        # mediterranean substitution dictionaries
        global mediterranean_substitutions_names
        global mediterranean_substitutions_adjectives
        global mediterranean_substitutions_categories
        global mediterranean_substitutions_exceptions
        print('\nMaking Mediterranean...')
        for step in self.steps:
            # make all ingredient substitutions
            make_substitutions_with(step.ingredients,
                                    self.ingredient_switches,
                                    mediterranean_substitutions_names,
                                    mediterranean_substitutions_adjectives,
                                    mediterranean_substitutions_categories,
                                    mediterranean_substitutions_exceptions,
                                    False)
        self.alter_steps()
        print('\nAltered Steps:')
        for step in self.steps:
            print(step)

    def print_recipe(self):
        # print information of a recipe
        print('\nName:', self.name)
        print('\nIngredients:')
        for ingredient in self.ingredients:
            print(ingredient)
        print('\nTools:', self.tools)
        print('\nPrimary Method:', self.primary_method)
        print('\nOther Methods:', self.other_methods)
        print('\nBaking?:', self.bake)
        print('\nSteps:')
        for step in self.steps:
            print(step)

    def jsonify(self):
        # make a recipe into a json format
        recipe = {'ingredients': self.ingredients,
                  'tools': self.tools,
                  'primary_method': self.primary_method,
                  'other_methods': self.other_methods,
                  'steps': self.steps}
        serializable = json.dumps(recipe)
        # pprint(serializable)
        return serializable


# step class definition

class Step:
    def __init__(self, step_text, ingredients):
        # each step has text, ingredients used in it, and methods used in it
        self.text = step_text
        self.ingredients = []
        self.methods = None
        ingredients_dict = {}
        # group ingredients by core name (excluding unique adjectives)
        for ingredient in ingredients:
            if ingredient.name in ingredients_dict:
                ingredients_dict[ingredient.name].append(ingredient)
            else:
                ingredients_dict[ingredient.name] = [ingredient]
        unique_ingredients_dict = {}
        # get all unique ingredient names by including adjectives
        for ingredient in ingredients_dict:
            if len(ingredients_dict[ingredient]) == 1:
                unique_ingredients_dict[ingredient] = ingredients_dict[ingredient][0]
            else:
                for ingredient_ref in ingredients_dict[ingredient]:
                    if ingredient_ref.adjective:
                        full_name = ingredient_ref.adjective + ' ' + ingredient
                        unique_ingredients_dict[full_name] = ingredient_ref
                    else:
                        unique_ingredients_dict[ingredient] = ingredient_ref
        for ingredient in unique_ingredients_dict:
            # if an ingredient is in the current step, add to the step's ingredient list
            if ingredient in step_text.lower():
                self.ingredients.append(unique_ingredients_dict[ingredient])

    def __str__(self):
        # print out ingredients and methods separately
        if debugging:
            output = self.text + '\nStep Ingredients:  '
            for ingredient in self.ingredients:
                output += str(ingredient) + ', '
            output = output[:-2] + '\nStep Methods:  '
            for method in self.methods:
                output += method + ', '
            return output[:-2]
        return self.text


# ingredient class definition

class Ingredient:
    def __init__(self, name, adjective, category, amount, unit):
        # each ingredient can have a core name, adjective descriptor, food category, amount, and unit
        self.name = name
        self.adjective = adjective
        self.category = category
        self.amount = amount
        self.unit = unit

    def __str__(self):
        output = ''
        # print out amount, unit, adjective, and name
        # i.e. 1 cup olive oil
        if self.amount:
            output += str(self.amount) + ' '
        if self.unit:
            output += self.unit + ' '
        if self.adjective:
            output += self.adjective + ' '
        return output + self.name


# ingredient instantiation functions

# create an ingredient which is the base of the source ingredient's adjective
def ingredient_base(ingredient):
    ingredient.name = ingredient.adjective
    ingredient.adjective = None
    return ingredient_categorize(ingredient)


# create an ingredient and categorize it
def ingredient_categorize(ingredient):
    # category = categorize(ingredient)
    # amount, unit = convert_measure(ingredient)
    # return Ingredient(ingredient.name, ingredient.adjective, category, amount, unit)
    return Ingredient(ingredient.name, ingredient.adjective, ingredient.category, ingredient.amount, ingredient.unit)


# make a new ingredient with a linearly proportionate amount
def ingredient_delta(name, adjective, category, delta, ingredient):
    return Ingredient(name, adjective, category, ingredient.amount*delta, ingredient.unit)


# make a completely new ingredient
def ingredient_ignore(name, adjective, category, amount, unit, ingredient):
    return Ingredient(name, adjective, category, amount, unit)


# substitution functions

# change the name to the input name and return with adjective if applicable
def change_name(name, ingredient):
    ingredient.name = name
    if ingredient.adjective:
        return ingredient.adjective + ' ' + ingredient.name
    return ingredient.name


# change the adjective of an ingredient and return the name and adjective full name
def change_adjective(adjective, ingredient):
    ingredient.adjective = adjective
    if ingredient.adjective:
        return ingredient.adjective + ' ' + ingredient.name
    return ingredient.name


# change the food category and return the name and adjective full name
def change_category(category, ingredient):
    ingredient.category = category
    if ingredient.adjective:
        return ingredient.adjective + ' ' + ingredient.name
    return ingredient.name


# change the amount of the ingredient and return the name, adjective full name
def change_amount(delta, ingredient):
    ingredient.amount *= delta
    if ingredient.adjective:
        return ingredient.adjective + ' ' + ingredient.name
    return ingredient.name


# change the unit of the ingredient and return the name, adjective full name
def change_unit(unit, ingredient):
    ingredient.unit = unit
    if ingredient.adjective:
        return ingredient.adjective + ' ' + ingredient.name
    return ingredient.name


# healthy substitutions dictionaries
# key: material to be replaced
# value: dictionary of partial functions later called with ingredient arguments to substitute/add/remove ingredients

healthy_substitutions_names = {
    'shortening': {'substitutions': [functools.partial(change_amount, 0.5)],
                   'additions': [functools.partial(ingredient_delta, 'applesauce', 'unsweetened', 'sauce', 1)],
                   'remove': None},
    'oil': {'substitutions': [functools.partial(change_adjective, 'olive')]},
    'butter': {'substitutions': [functools.partial(change_amount, 0.5)],
               'additions': [functools.partial(ingredient_delta, 'oil', 'olive', 'oil', 1)],
               'remove': None},
    'sugar': {'substitutions': [functools.partial(change_name, 'stevia')]},
    'salt': {'substitutions': [functools.partial(change_adjective, 'himalayan')]},
    'pasta': {'substitutions': [functools.partial(change_adjective, 'whole-wheat')]},
    'milk': {'substitutions': [functools.partial(change_adjective, 'almond')]},
    'cheese': {'substitutions': [functools.partial(change_amount, 0.5)]},
    'jelly': {'additions': [ingredient_base],
              'remove': None},
    'egg': {'substitutions': [functools.partial(change_adjective, 'substitute'),
                              functools.partial(change_amount, 0.25),
                              functools.partial(change_unit, 'cup')]},
    'rice': {'substitutions': [functools.partial(change_name, 'quinoa')]},
    'flour': {'substitutions': [functools.partial(change_adjective, 'whole-wheat')]},
    'chocolate': {'substitutions': [functools.partial(change_name, 'nibs'),
                                    functools.partial(change_adjective, 'cocoa')]},
    'beef': {'substitutions': [functools.partial(change_name, 'chicken')]},
    'steak': {'substitutions': [functools.partial(change_name, 'chicken')]},
    'bacon': {'substitutions': [functools.partial(change_adjective, 'turkey')]},
}
healthy_substitutions_adjectives = {
    'iceberg': {'substitutions': [functools.partial(change_adjective, 'romaine')]},
    'peanut': {'substitutions': [functools.partial(change_adjective, 'almond')]},
}
healthy_substitutions_categories = {
    'topping': {'remove': None},
    'condiment': {'remove': None},
    'vegetable': {'substitutions': [functools.partial(change_amount, 2)]},
}
healthy_substitutions_exceptions = {
    'peanut butter': {'substitutions': [functools.partial(change_adjective, 'almond')]},
    'sour cream': {'substitutions': [functools.partial(change_name, 'yogurt'),
                                     functools.partial(change_adjective, 'greek')]},
}
healthy_substitutions_methods = {
    'fry': 'saute'
}


# healthy baking substitutions dictionaries

healthy_baking_substitutions_names = {
    'shortening': {'substitutions': [functools.partial(change_amount, 0.5)],
                   'additions': [functools.partial(ingredient_delta, 'applesauce', 'unsweetened', 'sauce', 1)],
                   'remove': None},
    'oil': {'substitutions': [functools.partial(change_amount, 0.5)],
            'additions': [functools.partial(ingredient_delta, 'applesauce', 'unsweetened', 'sauce', 1)],
            'remove': None},
    'butter': {'substitutions': [functools.partial(change_amount, 0.5)],
               'additions': [functools.partial(ingredient_delta, 'applesauce', 'unsweetened', 'sauce', 1)],
               'remove': None},
    'sugar': {'substitutions': [functools.partial(change_name, 'stevia')]},
    'salt': {'substitutions': [functools.partial(change_adjective, 'himalayan')]},
    'milk': {'substitutions': [functools.partial(change_adjective, 'almond')]},
    'cheese': {'substitutions': [functools.partial(change_amount, 0.5)]},
    'jelly': {'additions': [ingredient_base],
              'remove': None},
    'egg': {'substitutions': [functools.partial(change_adjective, 'substitute'),
                              functools.partial(change_amount, 0.25),
                              functools.partial(change_unit, 'cup')]},
    'flour': {'substitutions': [functools.partial(change_adjective, 'whole-wheat')]},
    'chocolate': {'substitutions': [functools.partial(change_name, 'nibs'),
                                    functools.partial(change_adjective, 'cacao')]},
    'beef': {'substitutions': [functools.partial(change_name, 'chicken')]},
    'steak': {'substitutions': [functools.partial(change_name, 'chicken')]},
    'bacon': {'substitutions': [functools.partial(change_adjective, 'turkey')]},
}
healthy_baking_substitutions_adjectives = {
    'peanut': {'substitutions': [functools.partial(change_adjective, 'almond')]},
}
healthy_baking_substitutions_categories = {
    'topping': {'remove': None},
}
healthy_baking_substitutions_exceptions = {
    'peanut butter': {'substitutions': [functools.partial(change_adjective, 'almond')]},
}
healthy_baking_substitutions_methods = {
    'fry': 'bake'
}


# unhealthy substitutions dictionaries

unhealthy_substitutions_names = {
    'applesauce': {'substitutions': [functools.partial(change_amount, 3)],
                   'additions': [functools.partial(ingredient_delta, 'shortening', '', '', 1)],
                   'remove': None},
    'oil': {'substitutions': [functools.partial(change_amount, 3)],
            'additions': [functools.partial(ingredient_delta, 'butter', '', '', 1)],
            'remove': None},
    'stevia': {'substitutions': [functools.partial(change_name, 'sugar'),
                                 functools.partial(change_amount, 2)]},
    'salt': {'substitutions': [functools.partial(change_adjective, 'table'),
                               functools.partial(change_amount, 2)]},
    'pasta': {'substitutions': [functools.partial(change_adjective, '')]},
    'milk': {'substitutions': [functools.partial(change_adjective, 'whole')]},
    'cheese': {'substitutions': [functools.partial(change_amount, 2)]},
    'eggs': {'substitutions': [functools.partial(change_adjective, ''),
                               functools.partial(change_amount, 1),
                               functools.partial(change_unit, 'egg')]},
    'quinoa': {'substitutions': [functools.partial(change_name, 'rice'),
                                 functools.partial(change_adjective, 'white')]},
    'flour': {'substitutions': [functools.partial(change_adjective, '')]},
    'cacao': {'substitutions': [functools.partial(change_name, 'chocolate'),
                                functools.partial(change_adjective, '')]},
    'zoodles': {'additions': [functools.partial(ingredient_delta, 'pasta', '', '', 1)],
                'remove': None},
    'flaxseed': {'additions': [functools.partial(ingredient_delta, 'crumbs', 'bread', '', 1)],
                 'remove': None},
    'chicken': {'substitutions': [functools.partial(change_name, 'beef')]},
}
unhealthy_substitutions_adjectives = {
    'romaine': {'substitutions': [functools.partial(change_adjective, 'iceberg')]},
    'almond': {'substitutions': [functools.partial(change_adjective, 'peanut')]},
    'corn': {'substitutions': [functools.partial(change_adjective, 'flour')]},
    'fresh': {'substitutions': [functools.partial(change_adjective, 'canned')]},
}
unhealthy_substitutions_categories = {
    'vegetable': {'remove': None},
}
unhealthy_substitutions_exceptions = {
    'greek yogurt': {'substitutions': [functools.partial(change_name, 'sour'),
                                       functools.partial(change_adjective, 'cream')]},
}
unhealthy_substitutions_methods = {
    'saute': 'fry',
    'sauté': 'fry',
    'steam': 'fry',
    'grill': 'fry',
    'roast': 'fry',
    'bake': 'fry',
    'cook': 'fry'
}


# unhealthy baking substitutions dictionaries

unhealthy_baking_substitutions_names = {
    'applesauce': {'substitutions': [functools.partial(change_amount, 3)],
                   'additions': [functools.partial(ingredient_delta, 'shortening', '', '', 1)],
                   'remove': None},
    'oil': {'substitutions': [functools.partial(change_amount, 3)],
            'additions': [functools.partial(ingredient_delta, 'butter', '', '', 1)],
            'remove': None},
    'stevia': {'substitutions': [functools.partial(change_name, 'sugar'),
                                 functools.partial(change_amount, 2)]},
    'salt': {'substitutions': [functools.partial(change_adjective, 'table'),
                               functools.partial(change_amount, 2)]},
    'pasta': {'substitutions': [functools.partial(change_adjective, '')]},
    'milk': {'substitutions': [functools.partial(change_adjective, 'whole')]},
    'cheese': {'substitutions': [functools.partial(change_amount, 2)]},
    'egg': {'substitutions': [functools.partial(change_adjective, ''),
                              functools.partial(change_amount, 1),
                              functools.partial(change_unit, 'egg')]},
    'quinoa': {'substitutions': [functools.partial(change_name, 'rice'),
                                 functools.partial(change_adjective, 'white')]},
    'flour': {'substitutions': [functools.partial(change_adjective, '')]},
    'cacao': {'substitutions': [functools.partial(change_name, 'chocolate'),
                                functools.partial(change_adjective, '')]},
    'zoodles': {'additions': [functools.partial(ingredient_delta, 'pasta', '', '', 1)],
                'remove': None},
    'flaxseed': {'additions': [functools.partial(ingredient_delta, 'crumbs', 'bread', '', 1)],
                 'remove': None},
    'chicken': {'substitutions': [functools.partial(change_name, 'beef')]},
}
unhealthy_baking_substitutions_adjectives = {
    'romaine': {'substitutions': [functools.partial(change_adjective, 'iceberg')]},
    'almond': {'substitutions': [functools.partial(change_adjective, 'peanut')]},
    'corn': {'substitutions': [functools.partial(change_adjective, 'flour')]},
    'fresh': {'substitutions': [functools.partial(change_adjective, 'canned')]},
}
unhealthy_baking_substitutions_categories = {
    'vegetable': {'remove': None},
}
unhealthy_baking_substitutions_exceptions = {
    'greek yogurt': {'substitutions': [functools.partial(change_name, 'sour'),
                                       functools.partial(change_adjective, 'cream')]},
}
unhealthy_baking_substitutions_methods = {
    'saute': 'fry',
    'sauté': 'fry',
    'steam': 'fry',
    'grill': 'fry',
    'roast': 'fry',
    'cook': 'fry'
}


# vegetarian substitutions dictionaries

vegetarian_substitutions_names = {
    'broth': {'substitutions': [functools.partial(change_adjective, 'vegetable'),
                                functools.partial(change_category, 'broth')]},
}
vegetarian_substitutions_adjectives = {}
vegetarian_substitutions_categories = {
    'chicken': {'substitutions': [functools.partial(change_name, 'eggplant'),
                                  functools.partial(change_adjective, None),
                                  functools.partial(change_category, 'vegetable')]},
    'pork': {'substitutions': [functools.partial(change_name, 'tofu'),
                               functools.partial(change_adjective, None),
                               functools.partial(change_category, 'curd')]},
    'beef': {'substitutions': [functools.partial(change_name, 'lentils'),
                               functools.partial(change_adjective, None),
                               functools.partial(change_category, 'vegetable')]},
    'sausage': {'substitutions': [functools.partial(change_name, 'seitan'),
                                  functools.partial(change_adjective, None),
                                  functools.partial(change_category, 'vegetable')]},
    'steak': {'substitutions': [functools.partial(change_name, 'mushroom'),
                                functools.partial(change_adjective, 'portobello'),
                                functools.partial(change_category, 'vegetable')]},
    'bacon': {'substitutions': [functools.partial(change_adjective, 'seitan'),
                                functools.partial(change_adjective, None),
                                functools.partial(change_category, 'vegetable')]},
    'fish': {'substitutions': [functools.partial(change_name, 'tofu'),
                               functools.partial(change_adjective, None),
                               functools.partial(change_category, 'curd')]},
    'crawfish': {'substitutions': [functools.partial(change_name, 'tofu'),
                                   functools.partial(change_adjective, None),
                                   functools.partial(change_category, 'curd')]},
    'crayfish': {'substitutions': [functools.partial(change_name, 'tofu'),
                                   functools.partial(change_adjective, None),
                                   functools.partial(change_category, 'curd')]},
    'tuna': {'substitutions': [functools.partial(change_name, 'tofuna'),
                               functools.partial(change_adjective, None),
                               functools.partial(change_category, 'curd')]},
    'trout': {'substitutions': [functools.partial(change_name, 'tempeh'),
                                functools.partial(change_adjective, None),
                                functools.partial(change_category, 'vegetable')]},
    'carp': {'substitutions': [functools.partial(change_name, 'tempeh'),
                               functools.partial(change_adjective, None),
                               functools.partial(change_category, 'vegetable')]},
    'flounder': {'substitutions': [functools.partial(change_name, 'tofu'),
                                   functools.partial(change_adjective, None),
                                   functools.partial(change_category, 'curd')]},
    'bass': {'substitutions': [functools.partial(change_name, 'tofu'),
                               functools.partial(change_adjective, None),
                               functools.partial(change_category, 'curd')]},
    'sturgeon': {'substitutions': [functools.partial(change_name, 'tofu'),
                                   functools.partial(change_adjective, None),
                                   functools.partial(change_category, 'curd')]},
    'shrimp': {'substitutions': [functools.partial(change_name, 'shrimp'),
                                 functools.partial(change_adjective, 'vegan'),
                                 functools.partial(change_category, 'curd')]},
    'salmon': {'substitutions': [functools.partial(change_name, 'salmon'),
                                 functools.partial(change_adjective, 'vegan'),
                                 functools.partial(change_category, 'vegetable')]},
    'lobster': {'substitutions': [functools.partial(change_name, 'lobster'),
                                  functools.partial(change_adjective, 'vegan'),
                                  functools.partial(change_category, 'curd')]},
    'scallops': {'substitutions': [functools.partial(change_name, 'tofu'),
                                   functools.partial(change_adjective, None),
                                   functools.partial(change_category, 'curd')]},
    'lamb': {'substitutions': [functools.partial(change_name, 'seitan'),
                               functools.partial(change_adjective, None),
                               functools.partial(change_category, 'vegetable')]},
    'crab': {'substitutions': [functools.partial(change_name, 'crab'),
                               functools.partial(change_adjective, 'vegan'),
                               functools.partial(change_category, 'vegetable')]},
    'turkey': {'substitutions': [functools.partial(change_name, 'tofurkey'),
                                 functools.partial(change_adjective, None),
                                 functools.partial(change_category, 'curd')]},
    'duck': {'substitutions': [functools.partial(change_name, 'duck'),
                               functools.partial(change_adjective, 'mock'),
                               functools.partial(change_category, 'vegetable')]},
    'liver': {'substitutions': [functools.partial(change_name, 'liver'),
                                functools.partial(change_adjective, 'mock'),
                                functools.partial(change_category, 'vegetable')]},
    'ribs': {'substitutions': [functools.partial(change_name, 'seitan'),
                               functools.partial(change_adjective, None),
                               functools.partial(change_category, 'vegetable')]},
    'pheasant': {'substitutions': [functools.partial(change_name, 'eggplant'),
                                   functools.partial(change_adjective, None),
                                   functools.partial(change_category, 'vegetable')]},
    'quail': {'substitutions': [functools.partial(change_name, 'eggplant'),
                                functools.partial(change_adjective, None),
                                functools.partial(change_category, 'vegetable')]},
    'goose': {'substitutions': [functools.partial(change_name, 'eggplant'),
                                functools.partial(change_adjective, None),
                                functools.partial(change_category, 'vegetable')]},
    'escargot': {'substitutions': [functools.partial(change_name, 'tofu'),
                                   functools.partial(change_adjective, None),
                                   functools.partial(change_category, 'curd')]},
    'snail': {'substitutions': [functools.partial(change_name, 'tofu'),
                                functools.partial(change_adjective, None),
                                functools.partial(change_category, 'curd')]},
}
vegetarian_substitutions_exceptions = {}


# non-vegetarian substitutions dictionaries

non_vegetarian_substitutions_names = {
    'eggplant': {'substitutions': [functools.partial(change_name, 'chicken'),
                                   functools.partial(change_adjective, 'fried'),
                                   functools.partial(change_category, 'meat')]},
    'tofu': {'substitutions': [functools.partial(change_name, 'pork'),
                               functools.partial(change_category, 'meat')]},
    'lentils': {'substitutions': [functools.partial(change_name, 'beef'),
                                  functools.partial(change_category, 'meat')]},
    'mushroom': {'substitutions': [functools.partial(change_name, 'steak'),
                                   functools.partial(change_adjective, ''),
                                   functools.partial(change_category, 'meat')]},
    'seitan': {'substitutions': [functools.partial(change_name, 'bacon'),
                                 functools.partial(change_category, 'meat')]},
    'tempeh': {'substitutions': [functools.partial(change_name, 'fish'),
                                 functools.partial(change_category, 'meat')]},
}
non_vegetarian_substitutions_adjectives = {}
non_vegetarian_substitutions_categories = {}
non_vegetarian_substitutions_exceptions = {}


# thai substitutions dictionaries

thai_substitutions_names = {
    'salt': {'substitutions': [functools.partial(change_name, 'fish sauce'),
                               functools.partial(change_adjective, 'thai'),
                               functools.partial(change_amount, 1),
                               functools.partial(change_unit, 'tablespoon')]},
    'broccoli': {'substitutions': [functools.partial(change_adjective, 'chinese')]},
    'pasta': {'substitutions': [functools.partial(change_adjective, 'rice'),
                                functools.partial(change_name, 'noodles')]},
    'noodles': {'substitutions': [functools.partial(change_adjective, 'rice')]},
    'milk': {'substitutions': [functools.partial(change_adjective, 'coconut')]},
    'cream': {'substitutions': [functools.partial(change_adjective, 'coconut'),
                                functools.partial(change_name, 'milk')]},
    'onions': {'substitutions': [functools.partial(change_name, 'shallots')]},
    'onion': {'substitutions': [functools.partial(change_name, 'shallot')]},
    'basil': {'substitutions': [functools.partial(change_adjective, 'thai')]},
    'sugar': {'substitutions': [functools.partial(change_adjective, 'palm')]},
    'apple': {'substitutions': [functools.partial(change_name, 'mango'),
                                functools.partial(change_adjective, 'green')]},
    'turnip': {'substitutions': [functools.partial(change_name, 'radish'),
                                 functools.partial(change_adjective, 'white')]},
}
thai_substitutions_adjectives = {
    'whole-wheat': {'substitutions': [functools.partial(change_adjective, 'rice')]},
}
thai_substitutions_categories = {
    'pepper': {'substitutions': [functools.partial(change_adjective, 'chili')]}
}
thai_substitutions_exceptions = {
    'soy sauce': [functools.partial(change_name, 'fish sauce'),
                  functools.partial(change_adjective, 'thai')],
    'lemon zest': [functools.partial(change_name, 'lemongrass'),
                   functools.partial(change_adjective, None),
                   functools.partial(change_category, 'herb')],
    'large onion': {'substitutions': [functools.partial(change_name, 'shallots')]}
}


# mediterranean substitutions dictionaries

mediterranean_substitutions_names = {
    'broth': {'substitutions': [functools.partial(change_adjective, 'vegetable'),
                                functools.partial(change_category, 'broth')]},
    'tofu': {'substitutions': [functools.partial(change_name, 'fish'),
                               functools.partial(change_category, 'meat')]},
    'butter': {'substitutions': [functools.partial(change_name, 'olive oil'),
                                 functools.partial(change_category, 'healthy_fats')]},
    'soybean oil': {'substitutions': [functools.partial(change_name, 'sesame oil')]},
    'corn oil': {'substitutions': [functools.partial(change_name, 'olive oil')]},
    'vegetable oil': {'substitutions': [functools.partial(change_name, 'olive oil')]},
    'cottonseed oil': {'substitutions': [functools.partial(change_name, 'flaxseed oil')]},
    'bread': {'substitutions': [functools.partial(change_name, 'pita')]},
    'jelly': {'substitutions': [functools.partial(change_name, 'berries'),
                                functools.partial(change_adjective, 'fresh')]},
    'rice': {'substitutions': [functools.partial(change_adjective, 'wild'),
                               functools.partial(change_category, 'healthy_grains')]},
    'pasta': {'substitutions': [functools.partial(change_adjective, 'whole-wheat'),
                                functools.partial(change_category, 'healthy_grains')]},
    'flour': {'substitutions': [functools.partial(change_adjective, 'whole-wheat')]},
}
mediterranean_substitutions_adjectives = {}
mediterranean_substitutions_categories = {
    'unhealthy_fats': {'substitutions': [functools.partial(change_name, 'olive oil'),
                                         functools.partial(change_category, 'healthy_fats')]},
    'unhealthy_dairy': {'substitutions': [functools.partial(change_name, 'yogurt'),
                                          functools.partial(change_adjective, 'greek'),
                                          functools.partial(change_category, 'healthy_dairy')]},
    'beef': {'substitutions': [functools.partial(change_name, 'salmon'),
                               functools.partial(change_adjective, 'fillet')]},
    'chicken': {'substitutions': [functools.partial(change_name, 'tuna'),
                                  functools.partial(change_adjective, 'fillet')]},
    'turkey': {'substitutions': [functools.partial(change_name, 'beans'),
                                 functools.partial(change_adjective, None)]},
    'pork': {'substitutions': [functools.partial(change_name, 'trout'),
                               functools.partial(change_adjective, 'fillet')]},
    'bacon': {'substitutions': [functools.partial(change_name, 'salmon'),
                                functools.partial(change_adjective, None)]},
    'sausage': {'substitutions': [functools.partial(change_name, 'lentils')]},
}
mediterranean_substitutions_exceptions = {}


# helper functions

# create ingredient instance from information of ingredient_text
def add_ingredient(ingredient_text):
    global INGREDIENT_CATEGORIES
    global SYNONYMS
    adjective = None
    category = None
    amount = None
    unit = None
    ingredient_parts = ingredient_text.split(', ')  # split phrases if applicable
    ingredient = ingredient_parts[0]
    if len(ingredient_parts) > 1:
        ingredient_style = ingredient_parts[1]  # add latter phrase as style
    if 'to taste' in ingredient:
        if debugging:
            print('\ningred name:', ingredient.replace(' to taste', ''))
        return Ingredient(ingredient.replace(' to taste', ''), None, None, None, None)  # adjust for salt and pepper
    ingredient_words = ingredient.split()  # split ingredient into words
    name = ingredient_words[-1]  # assign last word to name
    ingredient_words = ingredient_words[:-1]
    if ingredient_words and ingredient_words[0][0].isdigit():  # if words start with a number, make it the amount
        if '/' in ingredient_words[0]:  # fractions
            amount_split = ingredient_words[0].split('/')
            amount = int(amount_split[0]) / int(amount_split[1])
        else:
            amount = float(ingredient_words[0])
        ingredient_words = ingredient_words[1:]
    if ingredient_words and amount:
        if ingredient_words[0][0] == '(' and ingredient_words[0][1].isdigit():  # account for alternative measurements
            amount = ingredient_words[0][1:]
            unit = ingredient_words[1][:-1]
            ingredient_words = ingredient_words[2:]
        else:
            pos = set()
            for synset in nltk.corpus.wordnet.synsets(ingredient_words[0]):  # get POS tagging for the word
                if synset.name().split('.')[0] == ingredient_words[0]:
                    pos.add(synset.pos())
            if 'a' not in pos and 's' not in pos:  # if not an adjective, add it as the amount
                unit = ingredient_words[0]
                ingredient_words = ingredient_words[1:]
    for word in ingredient_words:
        pos = set()
        for synset in nltk.corpus.wordnet.synsets(word):  # POS tagging
            if synset.name().split('.')[0] == word:
                pos.add(synset.pos())
        if not pos or 'a' in pos or 's' in pos or 'v' in pos:  # if word is an adjective or verb, add to adjective
            if not adjective:
                adjective = word
            else:
                adjective += ' ' + word
            ingredient_words = ingredient_words[1:]
        else:
            break
    for word in ingredient_words:
        if not adjective:
            adjective = word
        else:
            adjective += ' ' + word
    # if ingredient_words:
    #     prefix = ''
    #     for word in ingredient_words:
    #         prefix += word + ' '
    #     name = prefix + name
    if name in SYNONYMS:
        name = SYNONYMS[name]  # replace synonyms
    full_name = name
    if adjective:
        full_name = adjective + name
    for meat in INGREDIENT_CATEGORIES['meat']:  # categorize meats
        if meat in full_name:
            category = meat
    for key, val in INGREDIENT_CATEGORIES.items():  # categorize other types of ingredients
        if (full_name in val or name in val) and category is None:
            category = key
    if debugging:
        print('\ningred amt:', str(amount))
        print('ingred unit:', unit)
        print('ingred adj:', adjective)
        print('ingred name:', name)
        print('ingred cat:', category)
    return Ingredient(name, adjective, category, amount, unit)


# substitute ingredients, parametrized with ingredients and substitution dictionaries
def make_substitutions_with(ingredients, ingredient_switches, names, adjectives, categories, exceptions, vegetarian):
    global INGREDIENT_CATEGORIES
    added_ingredients = []
    removed_ingredients = []
    for ingredient in ingredients:  # for every ingredient
        name = ingredient.name
        full_name = name
        if ingredient.adjective:
            full_name = ingredient.adjective + ' ' + full_name
        if full_name in exceptions:  # make exceptions substitutions
            removed, new_name = make_substitutions(ingredient, exceptions[full_name], added_ingredients)
            ingredient_switches[full_name] = new_name  # add full name to ingredient_switches dict
            ingredient_switches[name] = new_name  # and after, name (full name is triggered first)
            if removed:
                removed_ingredients.append(ingredient)
            continue
        if name in names:  # name substitutions
            removed, new_name = make_substitutions(ingredient, names[name], added_ingredients)
            ingredient_switches[full_name] = new_name
            ingredient_switches[name] = new_name
            if removed:
                removed_ingredients.append(ingredient)
                continue
        if ingredient.adjective in adjectives:  # adjective substitutions
            removed, new_name = make_substitutions(ingredient, adjectives[ingredient.adjective], added_ingredients)
            ingredient_switches[full_name] = new_name
            ingredient_switches[name] = new_name
            if removed:
                removed_ingredients.append(ingredient)
                continue
        if ingredient.category in categories:  # category substitutions
            category = ingredient.category
            removed, new_name = make_substitutions(ingredient, categories[category], added_ingredients)
            ingredient_switches[full_name] = new_name
            ingredient_switches[name] = new_name
            if vegetarian and category in INGREDIENT_CATEGORIES['meat']:  # exception for vegetarian
                ingredient_switches['meat'] = new_name
                if new_name.split(' ')[-1] != category:  # len(new_name.split(' ')) > 2:
                    ingredient_switches[' ' + category] = ''
            if removed:
                removed_ingredients.append(ingredient)
                continue
    for ingredient in removed_ingredients:  # remove ingredients
        ingredients.remove(ingredient)
    for added_ingredient in added_ingredients:  # add ingredients, combining if the same
        combined = False
        for ingredient in ingredients:
            if ingredient.name == added_ingredient.name and ingredient.adjective == added_ingredient.adjective:
                ingredient.amount += added_ingredient.amount
                combined = True
                break
        if not combined:
            ingredients.append(added_ingredient)


# use partial functions in substitution dictionaries to modify, add, or remove ingredients
def make_substitutions(ingredient, substitutions, added_ingredients):
    new_name = ''
    if 'substitutions' in substitutions:
        for substitution in substitutions['substitutions']:
            new_name = substitution(ingredient)
    if 'additions' in substitutions:
        for addition in substitutions['additions']:
            new_ingredient = addition(ingredient)
            added_ingredients.append(new_ingredient)
    if 'remove' in substitutions:
        return True, ''
    return False, new_name


if __name__ == '__main__':
    debugging = True
    # get URL from user input
    while True:
        if debugging:
            # url = 'https://www.allrecipes.com/recipe/173906/cajun-roasted-pork-loin/'
            # url = 'https://www.allrecipes.com/recipe/269944/shrimp-and-smoked-sausage-jambalaya/'
            url = str(input('Please provide a recipe URL: '))
        else:
            url = str(input('Please provide a recipe URL: '))
        if len(url) > 40 and url[:34] == 'https://www.allrecipes.com/recipe/':
            try:
                # take url and load recipe using beautiful soup
                soup = BeautifulSoup(urllib.request.urlopen(url), 'html.parser')
                # instantiate recipe object using soup
                recipe = Recipe(soup)
                break
            except Exception as e:
                print(e)
        print('Invalid input, please try again.\n')
    # get recipe transformation from user input
    while True:
        # if debugging:
        #     transformation = 'mediterranean'
        # else:
        transformation = input('\nHow would you like to transform your recipe? Type "healthy", "unhealthy",'
                                   '"vegetarian", "meatify", "mediterranean", or "thai" (without quotes): ')
        if transformation == 'healthy':
            recipe.make_healthy()
            break
        elif transformation == 'unhealthy':
            recipe.make_unhealthy()
            break
        elif transformation == 'vegetarian':
            recipe.make_vegetarian()
            break
        elif transformation == 'meatify':
            recipe.make_non_vegetarian()
            break
        elif transformation == 'thai':
            recipe.make_thai()
            break
        elif transformation == 'mediterranean':
            recipe.make_mediterranean()
            break
        print('Invalid input, please try again.')
