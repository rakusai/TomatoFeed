function p(t){ document.write(t); }
{% ifnotequal option.cs "def" %}
p('<link href="{{ APP_URI }}/styles/custom.css" rel="stylesheet" type="text/css" />');
{% endifnotequal %}
p('<ul class="ors_{{ option.cs }}">');

{% if cached %}
	/* Cached Data */
{% endif %}

{% for entry in entries %}
	p('<li><a href="{{ entry.link|addslashes }}">{{ entry.title|addslashes }}</a>');
	{%  if entry.updated_format %}
		p(' ({{ entry.updated_format }})');
	{% endif %}
	p('</li>');

{% endfor %}

{%  ifequal entries_count 0  %}
	p('<li>項目が見つかりません。</li>');
{% endifequal %}

p('</ul>');
